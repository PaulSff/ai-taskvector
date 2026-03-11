"""
RLSet pipeline: serving pipeline for a trained RL agent.
"""
from units.registry import UnitSpec, register_unit

RLSET_INPUT_PORTS: list[tuple[str, str]] = []
RLSET_OUTPUT_PORTS: list[tuple[str, str]] = []


def _noop_step(params: dict, inputs: dict, state: dict, dt: float) -> tuple[dict, dict]:
    return {}, state


def register_rl_set() -> None:
    register_unit(UnitSpec(
        type_name="RLSet",
        input_ports=RLSET_INPUT_PORTS,
        output_ports=RLSET_OUTPUT_PORTS,
        step_fn=_noop_step,
        description="Serving pipeline for a trained RL agent: inference_url/model_path, observation_source_ids, action_target_ids; use add_pipeline.",
        pipeline=True,
        template_path="units/pipelines/rl_set/workflow.json",
        runtime_scope=None,
    ))


__all__ = ["register_rl_set", "RLSET_INPUT_PORTS", "RLSET_OUTPUT_PORTS"]
