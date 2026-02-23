"""
Unit registry: maps unit type strings to implementations (ComfyUI-style NODE_CLASS_MAPPINGS).

Each UnitSpec defines:
- input_ports: ordered list of (port_name, port_type) for graph wiring
- output_ports: ordered list of (port_name, port_type)
- step_fn: callable(params, inputs, state, dt) -> (outputs, new_state)
- optional: export_template for code_block generation
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

PortSpec = tuple[str, str]  # (name, type e.g. "float", "flow", "temp")


@dataclass
class UnitSpec:
    """
    Specification for a unit type: ports and step function.

    step_fn(params: dict, inputs: dict, state: dict, dt: float) -> (outputs: dict, new_state: dict)
    - params: from Unit.params (type-specific config)
    - inputs: resolved from connections {port_name: value}
    - state: unit's internal state (mutable between steps)
    - dt: time step
    """

    type_name: str
    input_ports: list[PortSpec] = field(default_factory=list)
    output_ports: list[PortSpec] = field(default_factory=list)
    step_fn: Callable[..., tuple[dict[str, Any], dict[str, Any]]] | None = None
    export_template: str | None = None  # for code_block / graph export (future)

    def __post_init__(self) -> None:
        if self.step_fn is None:
            raise ValueError(f"UnitSpec {self.type_name} must have step_fn")


UNIT_REGISTRY: dict[str, UnitSpec] = {}


def register_unit(spec: UnitSpec) -> None:
    """Register a unit type. Overwrites if already present."""
    UNIT_REGISTRY[spec.type_name] = spec


def get_unit_spec(type_name: str) -> UnitSpec | None:
    """Return UnitSpec for type_name or None if not registered."""
    return UNIT_REGISTRY.get(type_name)
