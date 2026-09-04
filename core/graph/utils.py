from __future__ import annotations

import json
from collections.abc import MutableSequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

from core.graph.core_config import (
    CUSTOM_CODE_UNIT_TYPES,
    ORIGIN_LANGUAGE,
)
from core.normalizer.runtime_detector import runtime_label
from core.schemas.primitives import Data, JsonValue
from core.schemas.process_graph import Connection, PortSpec, Unit
from units.registry import get_unit_spec

if TYPE_CHECKING:
    from core.schemas.graph_edit_api import GraphEdit


# App setting: coding_is_allowed (read from config/app_settings.json so graph_edits has no gui dependency)
_CODING_IS_ALLOWED_KEY = "coding_is_allowed"
_CODING_IS_ALLOWED_DEFAULT = False


def add_unit(
    units: MutableSequence[Unit],
    unit_id: str,
    unit_type: str,
    *,
    params: Data | None = None,
    controllable: bool = False,
) -> Unit:
    """Return an existing unit or append and return a new one."""

    for unit in units:
        if unit.id == unit_id:
            return unit

    unit = Unit(
        id=unit_id,
        type=unit_type,
        controllable=controllable,
        params=params or {},
    )
    units.append(unit)
    return unit


def add_connection(
    connections: MutableSequence[Connection],
    from_id: str,
    to_id: str,
    *,
    from_port: str = "0",
    to_port: str = "0",
    connection_type: str | None = None,
) -> Connection:
    """Add and return a connection unless an identical one already exists."""

    connection = Connection.model_validate(
        {
            "from": from_id,
            "to": to_id,
            "from_port": from_port,
            "to_port": to_port,
            "connection_type": connection_type,
        }
    )

    if connection not in connections:
        connections.append(connection)

    return connection

def ensure_unit_ports_from_registry(unit: Unit) -> None:
    """Set a unit's ports from the registry.

    Registry -> canonical graph model. Mutates ``unit`` in place.
    """
    spec = get_unit_spec(unit.type)

    if spec is not None:
        unit.input_ports = [
            PortSpec(name=name, type=port_type or None)
            for name, port_type in spec.input_ports
        ]
        unit.output_ports = [
            PortSpec(name=name, type=port_type or None)
            for name, port_type in spec.output_ports
        ]


def validate_connect_disconnect(parsed: GraphEdit) -> None:
    """Raise if connect/disconnect is missing required from/to parameters."""
    if parsed.action == "connect":
        if parsed.from_id is None or parsed.to_id is None:
            missing = [
                k
                for k, v in [("from", parsed.from_id), ("to", parsed.to_id)]
                if v is None
            ]
            raise ValueError(
                f"Incorrect format for connect: missing required parameter(s): {', '.join(missing)}"
            )
    elif parsed.action == "disconnect" and (
        parsed.from_id is None or parsed.to_id is None
    ):
        missing = [
            k
            for k, v in [("from", parsed.from_id), ("to", parsed.to_id)]
            if v is None
        ]
        raise ValueError(
            f"Incorrect format for disconnect: missing required parameter(s): {', '.join(missing)}"
        )


def duplicate_connection_exists(
    connections: list[Connection],
    *,
    from_id: str,
    to_id: str,
    from_port: str,
    to_port: str,
) -> bool:
    """Return whether an edge with the same source, target, and ports exists."""
    return any(
        connection.from_id == from_id
        and connection.to_id == to_id
        and connection.from_port == from_port
        and connection.to_port == to_port
        for connection in connections
    )

def assert_no_duplicate_connections(
    connections: list[Connection],
) -> None:
    """Raise if any two connections share the same endpoints and ports."""
    seen: set[tuple[str, str, str, str]] = set()

    for connection in connections:
        key = (
            connection.from_id,
            connection.to_id,
            connection.from_port,
            connection.to_port,
        )

        if key in seen:
            raise ValueError(
                "Duplicate connection: "
                + f"from={connection.from_id!r}, "
                + f"to={connection.to_id!r}, "
                + f"from_port={connection.from_port!r}, "
                + f"to_port={connection.to_port!r}"
            )

        seen.add(key)


def default_workflow_designer_prompt_path() -> str:
    """Return Workflow Designer prompt path from app settings when available, else default."""
    try:
        from gui.components.settings import get_workflow_designer_prompt_path

        return str(get_workflow_designer_prompt_path())
    except (ImportError, AttributeError):
        return "config/prompts/workflow_designer.json"


def coding_is_allowed() -> bool:
    """Return whether coding is enabled in app_settings.json."""
    try:
        repo_root = Path(__file__).resolve().parent.parent.parent
        config_path = repo_root / "config" / "app_settings.json"

        if not config_path.is_file():
            return _CODING_IS_ALLOWED_DEFAULT

        raw_data = cast(
            object,
            json.loads(config_path.read_text(encoding="utf-8")),
        )

        if not isinstance(raw_data, dict):
            return _CODING_IS_ALLOWED_DEFAULT

        data = cast(dict[str, JsonValue], raw_data)
        raw_value = data.get(_CODING_IS_ALLOWED_KEY)

        if isinstance(raw_value, bool):
            return raw_value

        return _CODING_IS_ALLOWED_DEFAULT

    except (OSError, json.JSONDecodeError):
        return _CODING_IS_ALLOWED_DEFAULT


def reject_custom_code_unit_if_disabled(unit_type: str) -> None:
    if coding_is_allowed():
        return
    if (unit_type or "").strip().lower() in CUSTOM_CODE_UNIT_TYPES:
        raise ValueError(
            "Custom code units (function / exec / script) are disabled. "
            + "Enable 'allow custom code' in app settings or use other unit types from the Units Library."
        )


def language_for_origin(origin: dict[str, JsonValue] | None) -> str | None:
    """Return expected code language from origin (runtime); uses centralized runtime_detector."""
    if not origin:
        return None
    rt = runtime_label({"origin": origin})
    return ORIGIN_LANGUAGE.get(rt)


def get_string_list(
    params: dict[str, JsonValue],
    key: str,
    fallback: set[str],
) -> list[str]:
    value = params.get(key)

    if not isinstance(value, list):
        return sorted(fallback)

    string_values = [
        item
        for item in value
        if isinstance(item, str)
    ]

    if len(string_values) != len(value):
        return sorted(fallback)  # or raise ValueError(...)

    return string_values or sorted(fallback)
