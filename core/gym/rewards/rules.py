"""
Rule-engine reward evaluator: evaluate RewardsConfig.rules against state.

State is built by the caller from outputs, goal, observation. Rules reference
variables in state via expressions (e.g. get(outputs, "unit_id.port", 0) - goal["target_temp"]).

Requires: rule-engine (see requirements.txt).
"""
from __future__ import annotations

from typing import Any

from core.schemas.training_config import RewardRule


def evaluate_rules(state: dict[str, Any], rules: list[RewardRule]) -> float:
    """
    Evaluate rule-engine rules against state; return sum of reward_delta for matching rules.

    state: dict from caller (outputs, goal, observation, step_count, and any derived vars).
    rules: list of RewardRule (condition, reward_delta). Condition is a rule-engine expression.
    """
    if not rules:
        return 0.0
    try:
        import rule_engine
    except ImportError:
        return 0.0

    total = 0.0
    for rule in rules:
        cond = rule.condition
        delta = rule.reward_delta
        if not cond:
            continue
        try:
            r = rule_engine.Rule(cond)
            if r.matches(state):
                total += float(delta)
        except Exception:
            continue
    return total
