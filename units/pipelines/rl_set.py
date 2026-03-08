"""
RLSet pipeline type: registered in the unit registry for description/tooling.
Pipeline type (add_pipeline), not executed as a graph unit; step_fn is a no-op.
"""
from units.registry import UnitSpec, register_unit

RLSET_INPUT_PORTS: list[tuple[str, str]] = []
RLSET_OUTPUT_PORTS: list[tuple[str, str]] = []


def _noop_step(params: dict, inputs: dict, state: dict, dt: float) -> tuple[dict, dict]:
    """No-op; pipeline nodes are not executed by the graph."""
    return {}, state


def register_rl_set() -> None:
    """Register RLSet in the unit registry (for description and type lookup)."""
    register_unit(UnitSpec(
        type_name="RLSet",
        input_ports=RLSET_INPUT_PORTS,
        output_ports=RLSET_OUTPUT_PORTS,
        step_fn=_noop_step,
        description="Serving pipeline for a trained RL agent: inference_url/model_path, observation_source_ids, action_target_ids; use add_pipeline.",
        pipeline=True,
        runtime_scope=None,
    ))


__all__ = ["register_rl_set", "RLSET_INPUT_PORTS", "RLSET_OUTPUT_PORTS"]
