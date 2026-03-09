"""
Reward evaluation: environment-agnostic formula and rules.

All reward calculation flows through evaluate_reward(). Context comes from
graph outputs (unit_id → port → value), goal, observation, step_count.
No env-specific logic or hardcoded parameters.
"""
from core.gym.rewards.formula import evaluate_reward
from core.gym.rewards.rules import evaluate_rules

__all__ = ["evaluate_reward", "evaluate_rules"]
