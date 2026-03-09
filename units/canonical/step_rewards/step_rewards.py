"""
StepRewards unit: canonical observation + reward + done for the step.

Inputs: observation (from Join), trigger (injected), outputs (optional; injected by executor).
State: step_count (incremented on step, reset on reset).
Params: max_steps, reward (RewardsConfig / rewards DSL dict or None).
Outputs: observation (pass-through), reward, done, payload.

Accepts the full rewards DSL: RewardsConfig with formula (expr + weight/reward) and
rules (condition → reward_delta). Context: outputs (full graph when provided),
goal, observation, step_count, max_steps. Same logic for inline and external.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

from units.canonical.step_driver import TRIGGER_RESET

STEP_REWARDS_INPUT_PORTS = [
    ("observation", "vector"),
    ("trigger", "any"),
    ("outputs", "any"),  # optional; executor injects full graph outputs for DSL
]
STEP_REWARDS_OUTPUT_PORTS = [
    ("observation", "vector"),
    ("reward", "float"),
    ("done", "bool"),
    ("payload", "any"),  # {observation, reward, done} for http_response
]

_STEP_COUNT_KEY = "step_count"


def _to_observation(val: Any) -> list[float]:
    """Normalize input to list of floats."""
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return [float(x) if isinstance(x, (int, float)) else 0.0 for x in val]
    return [float(val)]


def _step_rewards_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Produce observation (pass-through), reward, done from Join observation and trigger."""
    observation = _to_observation(inputs.get("observation"))
    trigger = inputs.get("trigger")

    step_count = int(state.get(_STEP_COUNT_KEY, 0))
    if trigger == TRIGGER_RESET:
        step_count = 0
    else:
        step_count += 1
    new_state = {**state, _STEP_COUNT_KEY: step_count}

    max_steps = int(params.get("max_steps", 600))
    done = step_count >= max_steps

    reward_cfg = params.get("reward")
    reward = 0.0
    if reward_cfg is not None:
        try:
            from core.schemas.training_config import GoalConfig, RewardsConfig
            from core.gym.rewards import evaluate_reward
            cfg = RewardsConfig.model_validate(reward_cfg) if isinstance(reward_cfg, dict) else reward_cfg
            goal = reward_cfg.get("goal") if isinstance(reward_cfg, dict) else getattr(reward_cfg, "goal", None)
            if goal is not None and isinstance(goal, dict):
                goal = GoalConfig.model_validate(goal)
            # Full graph outputs when provided (executor injects); else minimal for observation-only formulas
            outputs = inputs.get("outputs")
            if not isinstance(outputs, dict):
                outputs = {"observation": {str(i): v for i, v in enumerate(observation)}}
            reward = evaluate_reward(
                cfg,
                outputs,
                goal,
                observation,
                step_count,
                max_steps,
            )
        except Exception:
            pass

    payload = {"observation": observation, "reward": float(reward), "done": bool(done)}
    return (
        {
            "observation": observation,
            "reward": float(reward),
            "done": bool(done),
            "payload": payload,
        },
        new_state,
    )


def register_step_rewards() -> None:
    register_unit(UnitSpec(
        type_name="StepRewards",
        input_ports=STEP_REWARDS_INPUT_PORTS,
        output_ports=STEP_REWARDS_OUTPUT_PORTS,
        step_fn=_step_rewards_step,
        role="step_rewards",
        description="Computes reward from observation and goal; outputs reward and done for the training loop.",
    ))


__all__ = [
    "register_step_rewards",
    "STEP_REWARDS_INPUT_PORTS",
    "STEP_REWARDS_OUTPUT_PORTS",
]
