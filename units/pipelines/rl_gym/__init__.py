"""
RLGym pipeline: full training setup for the canonical runtime.

When added via add_pipeline, ensures canonical training topology (Join, Switch, StepDriver, Split, StepRewards).
Policy runs in the training loop (e.g. SB3), not in the graph.
"""
from units.registry import UnitSpec, register_unit

RLGYM_INPUT_PORTS: list[tuple[str, str]] = []
RLGYM_OUTPUT_PORTS: list[tuple[str, str]] = []


def _noop_step(params: dict, inputs: dict, state: dict, dt: float) -> tuple[dict, dict]:
    return {}, state


def register_rl_gym() -> None:
    register_unit(UnitSpec(
        type_name="RLGym",
        input_ports=RLGYM_INPUT_PORTS,
        output_ports=RLGYM_OUTPUT_PORTS,
        step_fn=_noop_step,
        environment_tags=["RL training"],
        environment_tags_are_agnostic=True,
        description="Full training pipeline marker: ensures canonical topology (Join, Switch, StepDriver, Split, StepRewards); policy runs in SB3 loop.",
        pipeline=True,
        template_path="units/pipelines/rl_gym/workflow.json",
        runtime_scope="canonical",
    ))


__all__ = ["register_rl_gym", "RLGYM_INPUT_PORTS", "RLGYM_OUTPUT_PORTS"]
