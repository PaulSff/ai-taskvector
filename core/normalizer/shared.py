"""
Shared canonicalization for the normalizer pipeline.
Import modules produce dicts; to_process_graph uses these helpers to build ProcessGraph.
"""
import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from os import PathLike
from typing import cast

from core.schemas.primitives import (
    JsonArray,
    JsonObject,
    JsonValue,
    WorkflowInputs,
    is_json_array,
    is_json_object,
    is_model_dumpable,
)

# Unit types and controllable flag come from the unit spec (units/registry.py). Canonical agent/oracle
# type names and their aliases are below (resolved in canonical_unit_type).
CANONICAL_RL_AGENT_TYPE = "RLAgent"
CANONICAL_LLM_AGENT_TYPE = "LLMAgent"
CANONICAL_RL_ORACLE_TYPE = "RLOracle"
CANONICAL_RL_GYM_TYPE = "RLGym"

_RL_AGENT_TYPE_ALIASES = {"rl_agent"}
_LLM_AGENT_TYPE_ALIASES = {"llm_agent"}
_RL_ORACLE_TYPE_ALIASES = {"rl_oracle"}
_RL_GYM_TYPE_ALIASES = {"rl_gym"}

def infer_environments_from_unit_types(unit_types: list[str]) -> list[str]:
    """
    Infer environment tags from unit types using the unit registry (type-agnostic).
    Each registered UnitSpec may set environment_tags (e.g. ["thermodynamic"], ["data_bi"], ["canonical"], ["RL training"]).
    Returns a sorted list of unique tags present in the graph. Call after all relevant unit modules are registered.
    """
    from units.registry import get_unit_spec

    seen: set[str] = set()
    for t in unit_types:
        if not t:
            continue
        spec = get_unit_spec(t)
        if spec and spec.environment_tags:
            for tag in spec.environment_tags:
                seen.add(tag)
    return sorted(seen)


def canonical_unit_type(typ: str) -> str:
    """Return canonical unit type. Resolves agent/oracle/gym aliases to RLAgent, LLMAgent, RLOracle, RLGym."""
    if not typ:
        return typ
    key = typ.strip()
    low = key.lower().replace("-", "_")
    if low in _RL_AGENT_TYPE_ALIASES or key == CANONICAL_RL_AGENT_TYPE:
        return CANONICAL_RL_AGENT_TYPE
    if low in _LLM_AGENT_TYPE_ALIASES or key == CANONICAL_LLM_AGENT_TYPE:
        return CANONICAL_LLM_AGENT_TYPE
    if low in _RL_ORACLE_TYPE_ALIASES or key == CANONICAL_RL_ORACLE_TYPE:
        return CANONICAL_RL_ORACLE_TYPE
    if low in _RL_GYM_TYPE_ALIASES or key == CANONICAL_RL_GYM_TYPE:
        return CANONICAL_RL_GYM_TYPE
    return key


def ensure_list_connections(raw: JsonValue) -> JsonArray:
    """Normalize connection objects and fill missing port indexes with '0'."""
    out: JsonArray = []

    if not is_json_array(raw):
        return out

    for value in raw:
        if not is_json_object(value):
            continue

        from_value = value.get("from") or value.get("from_id")
        to_value = value.get("to") or value.get("to_id")

        if from_value is None or to_value is None:
            continue

        from_port = value.get("from_port")
        to_port = value.get("to_port")

        entry: JsonObject = {
            "from": str(from_value),
            "to": str(to_value),
            "from_port": str(from_port) if from_port is not None else "0",
            "to_port": str(to_port) if to_port is not None else "0",
        }

        connection_type = value.get("connection_type")
        if connection_type is not None:
            entry["connection_type"] = str(connection_type)

        out.append(entry)

    return out


# ----- shared converters ----
def to_json_value(value: object) -> JsonValue:
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    # JSON has no native date/time types. Use ISO-8601 strings.
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    # Represent durations as seconds.
    if isinstance(value, timedelta):
        return value.total_seconds()

    # Represent filesystem paths as strings.
    if isinstance(value, PathLike):
        return str(value)

    # Represent enum members using their underlying values.
    if isinstance(value, Enum):
        return to_json_value(value.value)

    if isinstance(value, Mapping):
        json_object: JsonObject = {}

        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise TypeError(
                    "JSON object keys must be strings, "
                    f"got {type(key).__name__}"
                )

            json_object[key] = to_json_value(nested_value)

        return json_object

    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_json_value(item) for item in value]

    if is_model_dumpable(value):
        try:
            dumped = value.model_dump(
                by_alias=True,
                mode="json",
            )
        except TypeError:
            dumped = value.model_dump(by_alias=True)

        return to_json_value(dumped)

    if is_dataclass(value) and not isinstance(value, type):
        return to_json_value(asdict(value))

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_json_value(to_dict())

    raise TypeError(
        f"Value of type {type(value).__name__} is not JSON serializable: "
        f"{value!r}"
    )


def outputs_to_json_object(
    outputs: dict[str, dict[str, object]],
) -> JsonObject:
    json_outputs: JsonObject = {}

    for output_name, output_values in outputs.items():
        json_value = to_json_value(output_values)

        if not isinstance(json_value, dict):
            raise TypeError(
                f"Output {output_name!r} did not convert to a JSON object"
            )

        json_outputs[output_name] = json_value

    return json_outputs

def object_dict_to_json_object(
    values: dict[str, object],
) -> JsonObject:
    json_object: JsonObject = {}

    for key, value in values.items():
        json_object[key] = to_json_value(value)

    return json_object

def workflow_inputs_to_json_object(
    inputs: dict[str, dict[str, JsonValue]] | None,
) -> JsonObject | None:
    if inputs is None:
        return None

    json_inputs: JsonObject = {}

    for key, nested_inputs in inputs.items():
        json_inputs[key] = to_json_value(nested_inputs)

    return json_inputs

def as_workflow_inputs(
    value: JsonValue | None,
) -> WorkflowInputs | None:
    if not is_json_object(value):
        return None

    return {
        unit_id: override
        for unit_id, override in value.items()
        if is_json_object(override)
    }


def serialize(value: object) -> str:
    if value is None or value == "":
        return ""

    try:
        return json.dumps(value, indent=2, default=str)
    except TypeError:
        return str(value)


def as_object_dict(value: object) -> dict[object, object] | None:
    if isinstance(value, dict):
        return cast(dict[object, object], value)
    return None


def dump_json_object(value: object) -> JsonObject:
    if not is_model_dumpable(value):
        raise TypeError(
            f"Expected a model with model_dump(), got {type(value).__name__}"
        )

    dumped = value.model_dump(by_alias=True)

    if not is_json_object(dumped):
        raise TypeError("model_dump() did not return a JSON object")

    return dumped


def as_object(value: JsonValue | None, field_name: str) -> JsonObject:
    if value is None:
        return {}

    if not is_json_object(value):
        raise ValueError(f"{field_name} must be a mapping")

    return value
