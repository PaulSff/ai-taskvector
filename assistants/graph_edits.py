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


def apply_graph_edit(current: dict[str, Any], edit: dict[str, Any]) -> dict[str, Any]:
    """
    Apply a single graph edit to the current graph (dict).
    Returns updated dict suitable for normalizer.to_process_graph(updated, format="dict").
    Does not validate the result; normalizer will.
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

    elif parsed.action == "remove_unit" and parsed.unit_id is not None:
        uid = parsed.unit_id
        units = [x for x in units if x.get("id") != uid]
        connections = [c for c in connections if c.get("from") != uid and c.get("to") != uid]

    elif parsed.action == "connect" and parsed.from_id is not None and parsed.to_id is not None:
        connections.append({"from": parsed.from_id, "to": parsed.to_id})

    elif parsed.action == "disconnect" and parsed.from_id is not None and parsed.to_id is not None:
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
