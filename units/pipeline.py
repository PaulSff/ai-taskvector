"""
RLSet and LLMSet pipeline types: registered in the unit registry for description/tooling.
They are pipeline types (add_pipeline), not executed as graph units; step_fn is a no-op.
"""
from units.registry import UnitSpec, register_unit

PIPELINE_INPUT_PORTS: list[tuple[str, str]] = []
PIPELINE_OUTPUT_PORTS: list[tuple[str, str]] = []


def _noop_step(params: dict, inputs: dict, state: dict, dt: float) -> tuple[dict, dict]:
    """No-op; pipeline nodes are not executed by the graph."""
    return {}, state


def register_pipeline_units() -> None:
    """Register RLSet and LLMSet in the unit registry (for description and type lookup)."""
    register_unit(UnitSpec(
        type_name="RLSet",
        input_ports=PIPELINE_INPUT_PORTS,
        output_ports=PIPELINE_OUTPUT_PORTS,
        step_fn=_noop_step,
        description="Serving pipeline for a trained RL agent: inference_url/model_path, observation_source_ids, action_target_ids; use add_pipeline.",
    ))
    register_unit(UnitSpec(
        type_name="LLMSet",
        input_ports=PIPELINE_INPUT_PORTS,
        output_ports=PIPELINE_OUTPUT_PORTS,
        step_fn=_noop_step,
        description="LLM agent pipeline: model_name, provider, system_prompt, observation_source_ids, action_target_ids; use add_pipeline.",
    ))


__all__ = ["register_pipeline_units"]
