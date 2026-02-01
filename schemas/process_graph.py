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

    @property
    def from_unit(self) -> str:
        return self.from_id

    @property
    def to_unit(self) -> str:
        return self.to_id


class ProcessGraph(BaseModel):
    """Canonical process graph: environment type, units, connections."""

    environment_type: EnvironmentType = Field(
        default=EnvironmentType.THERMODYNAMIC,
        description="Environment type (thermodynamic, chemical, generic_control)",
    )
    units: list[Unit] = Field(default_factory=list, description="List of units")
    connections: list[Connection] = Field(default_factory=list, description="List of connections (from, to)")

    def get_unit(self, unit_id: str) -> Unit | None:
        """Return unit by id or None."""
        for u in self.units:
            if u.id == unit_id:
                return u
        return None
