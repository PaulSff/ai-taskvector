"""
RLAgent unit type: policy node.

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
    """No-op; RLAgent runs via adapters, not executor."""
    return {}, state


def register_agent_units() -> None:
    """Register RLAgent in the unit registry."""
    register_unit(UnitSpec(
        type_name="RLAgent",
        input_ports=[],  # From graph: connections into agent
        output_ports=[],  # From graph: connections from agent
        step_fn=_noop_step,
    ))


__all__ = ["register_agent_units"]
