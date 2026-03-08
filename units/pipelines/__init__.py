"""Pipeline types: RLGym, RLOracle, RLSet, LLMSet. Registered in the unit registry; use add_pipeline in graph edits."""

from units.pipelines.llm_set import register_llm_set
from units.pipelines.oracle import register_oracle_units
from units.pipelines.rl_gym import register_rl_gym
from units.pipelines.rl_set import register_rl_set


def register_all_pipelines() -> None:
    """Register all pipeline types in the unit registry. Idempotent."""
    register_rl_gym()
    register_oracle_units()
    register_rl_set()
    register_llm_set()


__all__ = [
    "register_all_pipelines",
    "register_rl_gym",
    "register_oracle_units",
    "register_rl_set",
    "register_llm_set",
]
