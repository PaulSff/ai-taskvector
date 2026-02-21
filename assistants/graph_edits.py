"""
Graph edit schema and apply logic for Process Assistant.
Edits are applied to a graph dict; then normalizer.to_process_graph(updated) yields canonical ProcessGraph.
"""
from typing import Any, Literal

from pydantic import BaseModel, Field


# Action types matching ENVIRONMENT_PROCESS_ASSISTANT.md §6
GraphEditAction = Literal["add_unit", "remove_unit", "connect", "disconnect", "no_edit", "replace_graph"]


class GraphEditUnit(BaseModel):
    """Unit payload for add_unit edit."""

    id: str = Field(..., description="Unique unit identifier")
    type: str = Field(..., description="Unit type: Source, Valve, Tank, Sensor, etc.")
    controllable: bool = Field(default=False, description="Whether this unit is an action/control input")
    params: dict[str, Any] = Field(default_factory=dict, description="Type-specific parameters")


class GraphEdit(BaseModel):
    """Structured graph edit from Process Assistant (validate in backend)."""

    action: GraphEditAction = Field(
        ..., description="add_unit | remove_unit | connect | disconnect | no_edit | replace_graph"
    )
    unit_id: str | None = Field(default=None, description="For remove_unit")
    unit: GraphEditUnit | None = Field(default=None, description="For add_unit")
    from_id: str | None = Field(default=None, alias="from", description="Source unit id for connect/disconnect")
    to_id: str | None = Field(default=None, alias="to", description="Target unit id for connect/disconnect")
    reason: str | None = Field(default=None, description="For no_edit")
    units: list[dict[str, Any]] | None = Field(default=None, description="For replace_graph: full unit list")
    connections: list[dict[str, str]] | None = Field(default=None, description="For replace_graph: full connection list")

    model_config = {"populate_by_name": True}


def _normalize_edit(edit: dict[str, Any]) -> dict[str, Any]:
    """If edit has units+connections but no action, treat as replace_graph."""
    if edit.get("action") is not None:
        return dict(edit)
    if isinstance(edit.get("units"), list) and isinstance(edit.get("connections"), list):
        return {**edit, "action": "replace_graph"}
    return dict(edit)


def _validate_connect_disconnect(parsed: GraphEdit) -> None:
    """Raise if connect/disconnect is missing required from/to parameters."""
    if parsed.action == "connect":
        if parsed.from_id is None or parsed.to_id is None:
            missing = [k for k, v in [("from", parsed.from_id), ("to", parsed.to_id)] if v is None]
            raise ValueError(
                f"Incorrect format for connect: missing required parameter(s): {', '.join(missing)}"
            )
    elif parsed.action == "disconnect":
        if parsed.from_id is None or parsed.to_id is None:
            missing = [k for k, v in [("from", parsed.from_id), ("to", parsed.to_id)] if v is None]
            raise ValueError(
                f"Incorrect format for disconnect: missing required parameter(s): {', '.join(missing)}"
            )


def apply_graph_edit(current: dict[str, Any], edit: dict[str, Any]) -> dict[str, Any]:
    """
    Apply a single graph edit to the current graph (dict).
    Returns updated dict suitable for normalizer.to_process_graph(updated, format="dict").
    Does not validate the result; normalizer will.
    Raises ValueError for invalid edits (missing params, non-existent unit/connection).
    """
    edit = _normalize_edit(edit)
    parsed = GraphEdit.model_validate(edit)
    if parsed.action == "no_edit":
        return dict(current)

    env_type = current.get("environment_type", "thermodynamic")
    units: list[dict[str, Any]] = [u.copy() for u in current.get("units", [])]
    connections: list[dict[str, str]] = []
    for c in current.get("connections", []):
        from_id = c.get("from") or c.get("from_id")
        to_id = c.get("to") or c.get("to_id")
        if from_id is not None and to_id is not None:
            connections.append({"from": str(from_id), "to": str(to_id)})

    if parsed.action == "add_unit" and parsed.unit is not None:
        u = parsed.unit
        if any(x["id"] == u.id for x in units):
            raise ValueError(f"Unit id already exists: {u.id}")
        units.append({
            "id": u.id,
            "type": u.type,
            "controllable": u.controllable,
            "params": dict(u.params),
        })

    elif parsed.action == "remove_unit":
        if parsed.unit_id is None:
            raise ValueError("Incorrect format for remove_unit: missing required parameter: unit_id")
        uid = parsed.unit_id
        if not any(x.get("id") == uid for x in units):
            raise ValueError(f"Unit id does not exist: {uid}")
        units = [x for x in units if x.get("id") != uid]
        connections = [c for c in connections if c.get("from") != uid and c.get("to") != uid]

    elif parsed.action == "connect":
        _validate_connect_disconnect(parsed)
        from_id, to_id = parsed.from_id, parsed.to_id
        unit_ids = {u.get("id") for u in units}
        if from_id not in unit_ids:
            raise ValueError(f"Unit id does not exist: {from_id}")
        if to_id not in unit_ids:
            raise ValueError(f"Unit id does not exist: {to_id}")
        connections.append({"from": from_id, "to": to_id})

    elif parsed.action == "disconnect":
        _validate_connect_disconnect(parsed)
        conn = {"from": parsed.from_id, "to": parsed.to_id}
        if conn not in connections:
            raise ValueError(
                f"Connection does not exist: from={parsed.from_id}, to={parsed.to_id}"
            )
        connections = [
            c for c in connections
            if not (c.get("from") == parsed.from_id and c.get("to") == parsed.to_id)
        ]

    elif parsed.action == "replace_graph" and parsed.units is not None and parsed.connections is not None:
        # Full graph replacement: normalize unit/connection dicts to have id, type, controllable, params / from, to
        units = []
        for u in parsed.units:
            if isinstance(u, dict):
                units.append({
                    "id": str(u.get("id", "")),
                    "type": str(u.get("type", "Unit")),
                    "controllable": bool(u.get("controllable", False)),
                    "params": dict(u.get("params", {})),
                })
        connections = []
        for c in parsed.connections:
            if isinstance(c, dict):
                from_id = c.get("from") or c.get("from_id")
                to_id = c.get("to") or c.get("to_id")
                if from_id is not None and to_id is not None:
                    connections.append({"from": str(from_id), "to": str(to_id)})

    return {
        "environment_type": env_type,
        "units": units,
        "connections": connections,
    }
