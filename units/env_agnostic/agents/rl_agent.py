"""
RLAgent unit type: policy node for reinforcement learning.

Ports: one input (observation) and one output (action). In the canonical scheme the
executor builds the observation vector from the first output of each unit connected
to the agent, and injects the action vector into each unit connected from the agent.
See docs/PROCESS_GRAPH_TOPOLOGY.md §5.2.
"""
from units.registry import UnitSpec, register_unit

RLAGENT_INPUT_PORTS = [("observation", "vector")]
RLAGENT_OUTPUT_PORTS = [("action", "vector")]


def _noop_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """No-op; policy nodes run via adapters, not executor."""
    return {}, state


def register_rl_agent() -> None:
    """Register RLAgent in the unit registry."""
    register_unit(UnitSpec(
        type_name="RLAgent",
        input_ports=RLAGENT_INPUT_PORTS,
        output_ports=RLAGENT_OUTPUT_PORTS,
        step_fn=_noop_step,
        description="Reinforcement-learning policy node: receives observation vector, outputs action vector; runs via SB3/adapter.",
    ))


__all__ = ["register_rl_agent", "RLAGENT_INPUT_PORTS", "RLAGENT_OUTPUT_PORTS"]
