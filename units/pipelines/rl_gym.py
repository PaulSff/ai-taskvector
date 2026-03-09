"""
RLGym unit type: full training setup for our own runtime.

When added to the graph, ensures canonical training topology:
  observations -> Join -> StepRewards; Switch -> actions; StepDriver -> Split -> simulators.
The policy runs in the training loop (e.g. SB3), not in the graph.
Params: observation_source_ids, action_target_ids, max_steps, reward (optional RewardsConfig).
"""
from units.registry import UnitSpec, register_unit

# No ports needed; RLGym is a config/marker node, excluded from execution.
RLGYM_INPUT_PORTS: list[tuple[str, str]] = []
RLGYM_OUTPUT_PORTS: list[tuple[str, str]] = []


def _noop_step(params: dict, inputs: dict, state: dict, dt: float) -> tuple[dict, dict]:
    """No-op; RLGym is not executed by the graph."""
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
        runtime_scope="canonical",
    ))


__all__ = ["register_rl_gym", "RLGYM_INPUT_PORTS", "RLGYM_OUTPUT_PORTS"]
