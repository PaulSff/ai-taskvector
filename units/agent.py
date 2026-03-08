"""
RLAgent and LLMAgent unit types: policy nodes.

Ports: one input (observation) and one output (action). In the canonical scheme the
executor builds the observation vector from the first output of each unit connected
to the agent, and injects the action vector into each unit connected from the agent.
See docs/PROCESS_GRAPH_TOPOLOGY.md §5.2.
"""
from units.registry import UnitSpec, register_unit

# One logical port each: observation in (from many sources), action out (to many targets)
AGENT_INPUT_PORTS = [("observation", "vector")]
AGENT_OUTPUT_PORTS = [("action", "vector")]


def _noop_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """No-op; policy nodes run via adapters, not executor."""
    return {}, state


def register_agent_units() -> None:
    """Register RLAgent and LLMAgent in the unit registry."""
    register_unit(UnitSpec(
        type_name="RLAgent",
        input_ports=AGENT_INPUT_PORTS,
        output_ports=AGENT_OUTPUT_PORTS,
        step_fn=_noop_step,
        description="Reinforcement-learning policy node: receives observation vector, outputs action vector; runs via SB3/adapter.",
    ))
    register_unit(UnitSpec(
        type_name="LLMAgent",
        input_ports=AGENT_INPUT_PORTS,
        output_ports=AGENT_OUTPUT_PORTS,
        step_fn=_noop_step,
        description="LLM-based policy node: receives observation, outputs action; runs via inference API/adapter.",
    ))


__all__ = ["register_agent_units"]
