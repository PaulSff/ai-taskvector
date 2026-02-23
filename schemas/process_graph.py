"""
Canonical process graph schema.
Single source of truth for process structure: units + connections.
"""
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EnvironmentType(str, Enum):
    """Supported environment types for the constructor."""

    THERMODYNAMIC = "thermodynamic"
    CHEMICAL = "chemical"
    GENERIC_CONTROL = "generic_control"


class Unit(BaseModel):
    """A single unit in the process graph (Source, Valve, Tank, Sensor, etc.)."""

    id: str = Field(..., description="Unique unit identifier")
    type: str = Field(..., description="Unit type: Source, Valve, Tank, Sensor, etc.")
    controllable: bool = Field(default=False, description="Whether this unit is an action/control input")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Type-specific parameters: Source (temp, max_flow); Valve (position_range, setpoint, max_flow); Tank (capacity, cooling_rate); Sensor (measure).",
    )


class Connection(BaseModel):
    """A connection between two units (flow or measurement)."""

    model_config = {"populate_by_name": True}

    from_id: str = Field(..., alias="from", description="Source unit id")
    to_id: str = Field(..., alias="to", description="Target unit id")
    from_port: str | None = Field(default=None, description="Optional source output port; omit for single-output units")
    to_port: str | None = Field(default=None, description="Optional target input port; omit for single-input units")

    @property
    def from_unit(self) -> str:
        return self.from_id

    @property
    def to_unit(self) -> str:
        return self.to_id


class CodeBlock(BaseModel):
    """Language-agnostic code block (e.g. function node, script). Stored for roundtrip; not executed by constructor."""

    id: str = Field(..., description="Unique id for this code block (referenced by nodes)")
    language: str = Field(..., description="Language tag: python, javascript, etc.")
    source: str = Field(default="", description="Raw source code (opaque string)")


class NodePosition(BaseModel):
    """Visual position of a unit on the canvas (top-left). Same idea as Node-RED node x, y."""

    x: float = Field(..., description="X coordinate (e.g. left in logical pixels)")
    y: float = Field(..., description="Y coordinate (e.g. top in logical pixels)")


class NodeRedTabMeta(BaseModel):
    """Metadata for a Node-RED tab (container), used for UI/roundtrip."""

    id: str = Field(..., description="Node-RED tab id")
    label: str | None = Field(default=None, description="Node-RED tab label (display name)")
    disabled: bool | None = Field(default=None, description="Whether the tab is disabled (if provided)")


class NodeRedOrigin(BaseModel):
    """Origin metadata specific to Node-RED imports/roundtrip."""

    tabs: list[NodeRedTabMeta] = Field(default_factory=list, description="Node-RED flow tabs")


class GraphOrigin(BaseModel):
    """Optional metadata about the imported workflow's original format."""

    node_red: NodeRedOrigin | None = Field(default=None, description="Node-RED origin metadata")
    pyflow: dict[str, Any] | None = Field(default=None, description="PyFlow origin marker")
    n8n: dict[str, Any] | None = Field(default=None, description="n8n origin marker")
    ryven: dict[str, Any] | None = Field(default=None, description="Ryven origin marker")

    model_config = {"extra": "ignore"}


class ProcessGraph(BaseModel):
    """Canonical process graph: environment type, units, connections.

    Optional:
    - code_blocks: preserved external code (Node-RED/PyFlow/etc.)
    - layout: per-unit visual positions
    - origin: external-format metadata preserved for roundtrip/UI (e.g. Node-RED tab labels)
    """

    environment_type: EnvironmentType = Field(
        default=EnvironmentType.THERMODYNAMIC,
        description="Environment type (thermodynamic, chemical, generic_control)",
    )
    units: list[Unit] = Field(default_factory=list, description="List of units")
    connections: list[Connection] = Field(default_factory=list, description="List of connections (from, to)")
    code_blocks: list[CodeBlock] = Field(
        default_factory=list,
        description="Optional code blocks (language-agnostic: id, language, source) for function/script nodes; see docs/WORKFLOW_EDITORS_AND_CODE.md",
    )
    layout: dict[str, NodePosition] | None = Field(
        default=None,
        description="Optional per-unit visual positions (unit_id -> {x, y}). When present, GUI uses these; when absent, uses auto layout. See docs/WORKFLOW_STORAGE_AND_ROUNDTRIP.md.",
    )
    origin: GraphOrigin | None = Field(
        default=None,
        description="Optional origin metadata for imported workflows (Node-RED tabs, etc.).",
    )
    origin_format: str | None = Field(
        default=None,
        description="Import format: node_red, pyflow, n8n, ryven, dict. Used for export validation (export only to same format).",
    )

    def get_unit(self, unit_id: str) -> Unit | None:
        """Return unit by id or None."""
        for u in self.units:
            if u.id == unit_id:
                return u
        return None
