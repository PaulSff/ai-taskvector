"""
Rule-engine reward evaluator: evaluate RewardsConfig.rules against current state.

Used at env step time: state dict (temp_error, volume, hot_flow, dump_flow, etc.)
+ list of RewardRule → sum of reward_delta for rules whose condition matches.

Requires: pip install rule-engine (optional; if not installed, evaluate_rules returns 0.0).
See docs/REWARD_RULES.md.
"""
from typing import Any

from schemas.training_config import RewardRule


def evaluate_rules(state: dict[str, Any], rules: list[RewardRule]) -> float:
    """
    Evaluate rule-engine rules against current state; return sum of reward_delta for matching rules.

    state: dict of variable names to values (e.g. temp_error, volume, hot_flow, cold_flow, dump_flow).
    rules: list of RewardRule (condition, reward_delta). Condition is a rule-engine expression.

    Returns:
        Sum of reward_delta for each rule where rule.matches(state) is True.
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
