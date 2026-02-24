"""
Environment-agnostic reward formula evaluator.

Context: outputs (unit_id → port → value from graph), goal, observation, step_count.
All parameters come from graph connections/ports and config. No hardcoded env logic.
"""
from __future__ import annotations

import math
from typing import Any

from schemas.training_config import FormulaComponent, GoalConfig, RewardRule, RewardsConfig

from rewards.rules import evaluate_rules


def _safe_get(d: Any, path: str, default: float = 0.0) -> float:
    """Safe nested dict access for DSL: get(outputs, 'unit_id.port', 0)."""
    if d is None or not path:
        return default
    for k in path.split("."):
        if isinstance(d, dict) and k in d:
            d = d[k]
        else:
            return default
    if isinstance(d, (int, float)):
        return float(d)
    if isinstance(d, (list, tuple)) and d:
        return float(d[0]) if isinstance(d[0], (int, float)) else default
    return default


def _build_context(
    outputs: dict[str, dict[str, Any]],
    goal: GoalConfig | dict[str, Any] | None,
    observation: list[float],
    step_count: int,
    max_steps: int = 600,
    action: list[float] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build evaluator context. No env-specific derivation."""
    goal_dict: dict[str, Any] = {}
    if goal is not None:
        if hasattr(goal, "model_dump"):
            goal_dict = goal.model_dump()
        elif isinstance(goal, dict):
            goal_dict = dict(goal)

    ctx: dict[str, Any] = {
        "outputs": outputs,
        "goal": goal_dict,
        "observation": observation,
        "step_count": step_count,
        "max_steps": max_steps,
        "action": action or [],
        "abs": abs,
        "min": min,
        "max": max,
        "get": _safe_get,
    }
    for name in ("sqrt", "sin", "cos", "tan", "log", "log10", "exp", "pow"):
        if hasattr(math, name):
            ctx[name] = getattr(math, name)
    if extra:
        ctx.update(extra)
    return ctx


def _evaluate_formula_components(
    components: list[FormulaComponent],
    ctx: dict[str, Any],
) -> float:
    """Evaluate formula components using asteval."""
    try:
        from asteval import Interpreter
    except ImportError:
        return 0.0

    aeval = Interpreter(usersym=ctx)
    total = 0.0
    for comp in components:
        try:
            val = aeval(comp.expr)
            if comp.weight is not None:
                try:
                    total += comp.weight * float(val)
                except (TypeError, ValueError):
                    pass
            elif comp.reward is not None:
                if val:
                    total += comp.reward
        except Exception:
            continue
    return total


def evaluate_reward(
    rewards_config: RewardsConfig | None,
    outputs: dict[str, dict[str, Any]],
    goal: GoalConfig | dict[str, Any] | None,
    observation: list[float],
    step_count: int,
    max_steps: int = 600,
    action: list[float] | None = None,
    extra_state: dict[str, Any] | None = None,
) -> float:
    """
    Evaluate reward from config. Single entry point. Fully environment-agnostic.

    Context from caller: outputs (graph unit_id → port → value), goal, observation.
    Returns 0.0 if rewards_config is None or evaluation fails.
    """
    if rewards_config is None:
        return 0.0

    ctx = _build_context(
        outputs=outputs,
        goal=goal,
        observation=observation,
        step_count=step_count,
        max_steps=max_steps,
        action=action,
        extra=extra_state,
    )
    total = 0.0

    if rewards_config.formula:
        total += _evaluate_formula_components(rewards_config.formula, ctx)

    if rewards_config.rules:
        state = dict(ctx)
        if extra_state:
            state.update(extra_state)
        total += evaluate_rules(state, rewards_config.rules)

    return float(total)
