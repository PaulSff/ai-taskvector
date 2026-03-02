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
    DATA_BI = "data_bi"


class PortSpec(BaseModel):
    """Named port (input or output) for roundtrip when the format has port names/types (e.g. ComfyUI, n8n)."""

    name: str = Field(..., description="Port name (e.g. 'model', 'main', 'input_0')")
    type: str | None = Field(
        default=None,
        description="Port type from source format (e.g. ComfyUI: 'MODEL', 'FLOAT'; n8n: 'main', 'ai_tool'). Preserved for roundtrip.",
    )


class Unit(BaseModel):
    """A single unit in the process graph (Source, Valve, Tank, Sensor, etc.)."""

    id: str = Field(..., description="Unique unit identifier")
    type: str = Field(..., description="Unit type: Source, Valve, Tank, Sensor, etc.")
    controllable: bool = Field(default=False, description="Whether this unit is an action/control input")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Type-specific parameters: Source (temp, max_flow); Valve (position_range, setpoint, max_flow); Tank (capacity, cooling_rate); Sensor (measure).",
    )
    name: str | None = Field(
        default=None,
        description="Optional display name (e.g. n8n node name, Node-RED label). Set on import when available.",
    )
    input_ports: list[PortSpec] | None = Field(
        default=None,
        description="Optional input port names/types; index i corresponds to to_port i. Set on import (ComfyUI, n8n) for roundtrip.",
    )
    output_ports: list[PortSpec] | None = Field(
        default=None,
        description="Optional output port names/types; index i corresponds to from_port i. Set on import (ComfyUI, n8n) for roundtrip.",
    )


class Connection(BaseModel):
    """A connection between two units (flow or measurement)."""

    model_config = {"populate_by_name": True}

    from_id: str = Field(..., alias="from", description="Source unit id")
    to_id: str = Field(..., alias="to", description="Target unit id")
    from_port: str = Field(
        default="0",
        description="Source output port index (required). Value is the port index, e.g. '0', '1'; optional port name when available.",
    )
    to_port: str = Field(
        default="0",
        description="Target input port index (required). Value is the port index, e.g. '0', '1'; optional port name when available.",
    )
    connection_type: str | None = Field(
        default=None,
        description="Optional connection type from source format (e.g. n8n: main, ai_tool, ai_languageModel). Preserved on import for roundtrip.",
    )

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


class TabFlow(BaseModel):
    """One flow per tab (Node-RED multi-tab). Single tab per flow: each tab has its own units and connections."""

    id: str = Field(..., description="Tab/flow id (Node-RED tab id)")
    label: str | None = Field(default=None, description="Tab label (display name)")
    disabled: bool | None = Field(default=None, description="Whether the tab is disabled (if provided)")
    units: list[Unit] = Field(default_factory=list, description="Units in this tab")
    connections: list[Connection] = Field(default_factory=list, description="Connections in this tab")


class NodeRedOrigin(BaseModel):
    """Origin metadata specific to Node-RED imports/roundtrip."""

    tabs: list[NodeRedTabMeta] = Field(default_factory=list, description="Node-RED flow tabs")


class GraphOrigin(BaseModel):
    """Optional metadata about the imported workflow's original format."""

    canonical: bool | None = Field(
        default=None,
        description="True when the graph is canonical (repo units, never imported or imported as canonical).",
    )
    node_red: NodeRedOrigin | None = Field(default=None, description="Node-RED origin metadata")
    pyflow: dict[str, Any] | None = Field(default=None, description="PyFlow origin marker")
    n8n: dict[str, Any] | None = Field(default=None, description="n8n origin marker")
    ryven: dict[str, Any] | None = Field(default=None, description="Ryven origin marker")
    comfyui: dict[str, Any] | None = Field(default=None, description="ComfyUI origin marker")

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
    tabs: list[TabFlow] | None = Field(
        default=None,
        description="Multi-tab flows (e.g. Node-RED). One tab per flow: each tab has its own units and connections. When non-empty, top-level units/connections mirror the first tab for backward compatibility.",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional graph-level metadata (readme, summary, gitOwners, etc.) preserved from import for roundtrip; applicable to any runtime.",
    )

    def get_unit(self, unit_id: str) -> Unit | None:
        """Return unit by id or None."""
        for u in self.units:
            if u.id == unit_id:
                return u
        return None
