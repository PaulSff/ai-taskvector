"""
LLMAgent unit type: policy node for LLM-based control.

Ports: one input (observation) and one output (action). In the canonical scheme the
executor builds the observation vector from the first output of each unit connected
to the agent, and injects the action vector into each unit connected from the agent.
See docs/PROCESS_GRAPH_TOPOLOGY.md §5.2.
"""
from units.registry import UnitSpec, register_unit

LLMAGENT_INPUT_PORTS = [("observation", "vector")]
LLMAGENT_OUTPUT_PORTS = [("action", "vector")]


def _noop_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """No-op; policy nodes run via adapters, not executor."""
    return {}, state


def register_llm_agent() -> None:
    """Register LLMAgent in the unit registry."""
    register_unit(UnitSpec(
        type_name="LLMAgent",
        input_ports=LLMAGENT_INPUT_PORTS,
        output_ports=LLMAGENT_OUTPUT_PORTS,
        step_fn=_noop_step,
        description="LLM-based policy node: receives observation, outputs action; runs via inference API/adapter.",
    ))


__all__ = ["register_llm_agent", "LLMAGENT_INPUT_PORTS", "LLMAGENT_OUTPUT_PORTS"]
