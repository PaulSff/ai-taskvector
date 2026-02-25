"""
Unit registry and graph-based simulation units.

Each unit type (Source, Valve, Tank, Sensor) is registered with:
- Input/output port specs
- step(params, inputs) -> outputs for NumPy execution
- Optional code_block template for graph export (Node-RED, PyFlow, n8n)

Users only connect units; all logic lives in registered implementations.
"""

from units.registry import UNIT_REGISTRY, UnitSpec, register_unit, get_unit_spec, is_controllable_type

__all__ = ["UNIT_REGISTRY", "UnitSpec", "register_unit", "get_unit_spec", "is_controllable_type"]
