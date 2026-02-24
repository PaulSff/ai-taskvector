"""
RLOracle unit type: step-handler node for external-runtime training.

Registered with UnitSpec for consistency; ports are defined by graph connections.
The graph executor excludes it from execution (handled by adapters).
"""
from units.registry import UnitSpec, register_unit


def _noop_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """No-op; RLOracle runs via adapters, not executor."""
    return {}, state


def register_oracle_units() -> None:
    """Register RLOracle in the unit registry."""
    register_unit(UnitSpec(
        type_name="RLOracle",
        input_ports=[],
        output_ports=[],
        step_fn=_noop_step,
    ))


__all__ = ["register_oracle_units"]
