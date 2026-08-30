import json
from typing import Any, cast

import yaml

from core.schemas.primitives import (
    FormatProcess,
    JsonDocument,
    JsonObject,
    is_json_object,
    is_json_value,
)
from core.schemas.process_graph import PortSpec


def ensure_env_agnostic_units_registered() -> None:
    """Ensure RLAgent, LLMAgent, canonical units, etc. are in the registry so get_unit_spec works for all graph unit types."""
    try:
        from units.register_env_agnostic import register_env_agnostic_units

        register_env_agnostic_units()
    except (ImportError, AttributeError):
        pass


def ensure_environment_units_registered(env_type: Any) -> None:
    """Ensure environment-specific units are in the registry (via units.env_loaders). No-op for UNSPECIFIED."""
    from units.env_loaders import ensure_environment_units_registered

    val = (
        getattr(env_type, "value", env_type) if env_type is not None else "unspecified"
    )
    if isinstance(val, str):
        val = val.lower().strip()
    if val and val != "unspecified":
        ensure_environment_units_registered(val)


def ensure_environments_units_registered(environments: list[str]) -> None:
    """Register unit modules for every runtime environment in the list (from env_loaders registry)."""
    from units.env_loaders import ensure_environment_units_registered

    for tag in environments:
        ensure_environment_units_registered(str(tag).strip().lower())


def parse_keep_alive(value: Any) -> bool:
    """Normalize the graph-level keep_alive flag."""
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"true", "1", "yes", "on"}:
            return True

        if normalized in {"false", "0", "no", "off", ""}:
            return False

    if isinstance(value, (int, float)):
        return value != 0

    return False


def parse_port_specs(raw: Any) -> list[PortSpec]:
    """Parse input_ports/output_ports from canonical dict (list of {name, type?}). Returns [] when missing or empty."""
    if not isinstance(raw, list) or not raw:
        return []
    out: list[PortSpec] = []
    for item in raw:
        if isinstance(item, dict) and item.get("name") is not None:
            out.append(
                PortSpec(
                    name=str(item["name"]),
                    type=str(item["type"]) if item.get("type") is not None else None,
                )
            )
        else:
            try:
                out.append(PortSpec.model_validate(item))
            except (TypeError, ValueError):
                pass
    return out


def parse_json_document(
    raw: str,
    *,
    format: FormatProcess,
) -> JsonDocument:
    try:
        value = cast(object, json.loads(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"raw for format={format!r} must be valid JSON"
        ) from exc

    if not is_json_value(value):
        raise ValueError(
            f"raw for format={format!r} must contain JSON-compatible values"
        )

    if isinstance(value, dict):
        return value

    if isinstance(value, list):
        return value

    raise TypeError(
        f"raw for format={format!r} must decode to an object or array"
    )


def require_json_object(
    value: JsonDocument,
    *,
    format: FormatProcess,
) -> JsonObject:
    if not is_json_object(value):
        raise ValueError(
            f"raw for format={format!r} must be a JSON object"
        )

    return value


def require_json_document(
    raw: JsonDocument | str,
    *,
    format: FormatProcess,
) -> JsonDocument:
    if isinstance(raw, str):
        return parse_json_document(raw, format=format)

    return raw


def load_yaml_object(text: str) -> JsonObject:
    loaded: object = yaml.safe_load(text) or {}

    if not is_json_object(loaded):
        raise ValueError("YAML training config must contain a mapping at the root")

    return loaded
