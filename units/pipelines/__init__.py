"""Pipeline types: RLGym, RLOracle, RLSet, LLMSet, ChatOrchestrator. Each pipeline lives in its own package with README and workflow.json."""

from units.pipelines.agent_orchestrator import register_chat_orchestrator
from units.pipelines.llm_set import register_llm_set
from units.pipelines.rl_gym import register_rl_gym
from units.pipelines.rl_oracle import register_oracle_units
from units.pipelines.rl_set import register_rl_set


def register_all_pipelines() -> None:
    """Register all pipeline types in the unit registry. Idempotent."""
    register_rl_gym()
    register_oracle_units()
    register_rl_set()
    register_llm_set()
    register_chat_orchestrator()


__all__ = [
    "register_all_pipelines",
    "register_chat_orchestrator",
    "register_rl_gym",
    "register_oracle_units",
    "register_rl_set",
    "register_llm_set",
]
