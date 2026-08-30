"""
Shared canonicalization for the normalizer pipeline.
Import modules produce dicts; to_process_graph uses these helpers to build ProcessGraph.
"""
import json
from typing import Any, cast

from core.schemas.primitives import (
    JsonObject,
    JsonValue,
    WorkflowInputs,
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


def ensure_list_connections(raw: list[Any]) -> list[dict[str, Any]]:
    """Ensure each connection has 'from', 'to', 'from_port', 'to_port'. Port indices default to '0' when missing. Preserves connection_type when present."""
    out: list[dict[str, Any]] = []
    for c in raw:
        if isinstance(c, dict):
            from_id = c.get("from") or c.get("from_id")
            to_id = c.get("to") or c.get("to_id")
            if from_id is not None and to_id is not None:
                from_port = c.get("from_port")
                to_port = c.get("to_port")
                entry: dict[str, Any] = {
                    "from": str(from_id),
                    "to": str(to_id),
                    "from_port": str(from_port) if from_port is not None else "0",
                    "to_port": str(to_port) if to_port is not None else "0",
                }
                if c.get("connection_type") is not None:
                    entry["connection_type"] = str(c["connection_type"])
                out.append(entry)
    return out


# ----- shared converters ----
def to_json_value(value: object) -> JsonValue:
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        typed_value = cast(dict[object, object], value)
        json_object: JsonObject = {}

        for key, nested_value in typed_value.items():
            if not isinstance(key, str):
                raise TypeError(
                    f"JSON object keys must be strings, got {type(key).__name__}"
                )

            json_object[key] = to_json_value(nested_value)

        return json_object

    if isinstance(value, list):
        typed_value = cast(list[object], value)

        return [
            to_json_value(item)
            for item in typed_value
        ]

    raise TypeError(
        f"Value of type {type(value).__name__} is not JSON serializable"
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
