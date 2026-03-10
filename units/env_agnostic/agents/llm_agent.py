"""
LLMAgent unit type: policy node for LLM-based control.

Ports: system_prompt (from Prompt unit in Merge->Prompt->LLMAgent pipeline), observation (vector),
and one output (action). When wired from Prompt, system_prompt is fed from the connection.
See docs/PROCESS_GRAPH_TOPOLOGY.md §5.2.
"""
from units.registry import UnitSpec, register_unit

LLMAGENT_INPUT_PORTS = [("system_prompt", "str"), ("observation", "vector")]
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
