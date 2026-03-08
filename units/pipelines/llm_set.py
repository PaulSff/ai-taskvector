"""
LLMSet pipeline type: registered in the unit registry for description/tooling.
Pipeline type (add_pipeline), not executed as a graph unit; step_fn is a no-op.
"""
from units.registry import UnitSpec, register_unit

LLMSET_INPUT_PORTS: list[tuple[str, str]] = []
LLMSET_OUTPUT_PORTS: list[tuple[str, str]] = []


def _noop_step(params: dict, inputs: dict, state: dict, dt: float) -> tuple[dict, dict]:
    """No-op; pipeline nodes are not executed by the graph."""
    return {}, state


def register_llm_set() -> None:
    """Register LLMSet in the unit registry (for description and type lookup)."""
    register_unit(UnitSpec(
        type_name="LLMSet",
        input_ports=LLMSET_INPUT_PORTS,
        output_ports=LLMSET_OUTPUT_PORTS,
        step_fn=_noop_step,
        description="LLM agent pipeline: model_name, provider, system_prompt, observation_source_ids, action_target_ids; use add_pipeline.",
        pipeline=True,
        runtime_scope=None,
    ))


__all__ = ["register_llm_set", "LLMSET_INPUT_PORTS", "LLMSET_OUTPUT_PORTS"]
