"""
Training config edit merge (TrainingConfig).
Partial config edits are deep-merged into current config; then normalizer.to_training_config(merged) yields canonical TrainingConfig.

Same role as graph_edits for the process graph: apply a structured edit to the canonical schema.
Reward DSL actions: reward_formula_add, reward_formula_set, reward_rules_add, reward_rules_set
expand into rewards config before merge.
"""
from __future__ import annotations

from typing import Any


def expand_reward_actions(edit: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """
    Expand reward DSL actions into a rewards config edit. Returns edit with action replaced by rewards merge.
    """
    action = edit.get("action")
    if action not in ("reward_formula_add", "reward_formula_set", "reward_rules_add", "reward_rules_set"):
        return edit

    rewards = dict((current.get("rewards") or {}))
    formula = list(rewards.get("formula") or [])
    rules = list(rewards.get("rules") or [])

    if action == "reward_formula_add":
        comp = {"expr": edit.get("expr", "")}
        if "weight" in edit:
            comp["weight"] = float(edit["weight"])
        if "reward" in edit:
            comp["reward"] = float(edit["reward"])
        if comp.get("expr"):
            formula.append(comp)
    elif action == "reward_formula_set":
        formula = list(edit.get("formula") or [])

    if action == "reward_rules_add":
        rule = {
            "condition": edit.get("condition", ""),
            "reward_delta": float(edit.get("reward_delta", 0)),
        }
        if rule.get("condition"):
            rules.append(rule)
    elif action == "reward_rules_set":
        rules = list(edit.get("rules") or [])

    return {"rewards": {**rewards, "formula": formula, "rules": rules}}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Deep-merge override into base. override wins for leaf values.
    Lists are replaced (not merged). Used for training config edits.
    """
    result = dict(base)
    for key, value in override.items():
        if key not in result:
            result[key] = value
        elif isinstance(value, dict) and isinstance(result[key], dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def apply_config_edit(current: dict[str, Any], edit: dict[str, Any]) -> dict[str, Any]:
    """
    Merge edit (partial training config) into current config.
    If edit contains {"action": "no_edit", "reason": "..."}, returns current unchanged.
    Reward DSL actions (reward_formula_add, etc.) are expanded before merge.
    Result is suitable for normalizer.to_training_config(merged, format="dict").
    """
    if edit.get("action") == "no_edit":
        return dict(current)
    expanded = expand_reward_actions(edit, current)
    return deep_merge(current, expanded)
