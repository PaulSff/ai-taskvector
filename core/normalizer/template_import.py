"""
Template-style import: map template/generic dict to canonical process graph dict.

Accepts:
- blocks / units
- links / connections
- optional environment_type or process_environment_type

Used by IDAES and generic templates.
"""

from core.normalizer.shared import ensure_list_connections
from core.schemas.primitives import (
    JsonArray,
    JsonObject,
    JsonValue,
    is_json_array,
    is_json_object,
)


def _first_non_none(
    value: JsonObject,
    *keys: str,
) -> JsonValue:
    for key in keys:
        candidate = value.get(key)
        if candidate is not None:
            return candidate
    return None


def _template_blocks(raw: JsonObject) -> list[JsonObject]:
    blocks = _first_non_none(raw, "blocks", "units")
    if not is_json_array(blocks):
        return []

    result: list[JsonObject] = []

    for value in blocks:
        if is_json_object(value):
            result.append(value)

    return result


def _template_links(raw: JsonObject) -> JsonArray:
    links = _first_non_none(raw, "links", "connections")
    if not is_json_array(links):
        return []

    return [
        link
        for link in links
        if is_json_object(link)
    ]


def _template_block_id(block: JsonObject) -> str | None:
    value = _first_non_none(block, "id", "name")

    if value is None:
        return None

    block_id = str(value).strip()
    return block_id or None


def _template_block_type(block: JsonObject) -> str | None:
    value = _first_non_none(
        block,
        "type",
        "unitType",
        "blockType",
    )

    if value is None:
        return None

    if is_json_object(value):
        value = value.get("name")

    if value is None:
        return None

    block_type = str(value).strip()
    return block_type or None


def _template_bool(
    value: JsonValue,
    default: bool = True,
) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() not in {
            "",
            "0",
            "false",
            "no",
            "off",
        }

    if isinstance(value, (int, float)):
        return value != 0

    return bool(value)


def _template_params(block: JsonObject) -> JsonObject:
    value = _first_non_none(block, "params", "parameters")

    if is_json_object(value):
        return dict(value)

    return {}


def _template_unit(block: JsonObject) -> JsonObject | None:
    block_id = _template_block_id(block)
    block_type = _template_block_type(block)

    if block_id is None or block_type is None:
        return None

    controllable_value = _first_non_none(
        block,
        "controllable",
        "is_control",
    )

    unit: JsonObject = {
        "id": block_id,
        "type": block_type,
        "controllable": _template_bool(controllable_value),
        "params": _template_params(block),
    }

    name = block.get("name")
    if isinstance(name, str) and name.strip():
        unit["name"] = name.strip()

    return unit


def to_canonical_dict(raw: JsonObject) -> JsonObject:
    environment_value = _first_non_none(
        raw,
        "environment_type",
        "process_environment_type",
    )
    environment_type = (
        str(environment_value).strip()
        if environment_value is not None
        else ""
    )

    units: JsonArray = []
    seen_ids: set[str] = set()

    for block in _template_blocks(raw):
        unit = _template_unit(block)
        if unit is None:
            continue

        unit_id = unit["id"]
        if not isinstance(unit_id, str) or unit_id in seen_ids:
            continue

        seen_ids.add(unit_id)
        units.append(unit)

    connections = ensure_list_connections(_template_links(raw))

    return {
        "environment_type": environment_type,
        "units": units,
        "connections": connections,
    }
