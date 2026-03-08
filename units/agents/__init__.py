"""Policy unit types: RLAgent, LLMAgent. Used in both canonical and external runtimes (add_unit)."""

from units.agents.llm_agent import register_llm_agent
from units.agents.rl_agent import register_rl_agent


def register_all_agents() -> None:
    """Register RLAgent and LLMAgent in the unit registry. Idempotent."""
    register_rl_agent()
    register_llm_agent()


__all__ = ["register_all_agents", "register_rl_agent", "register_llm_agent"]
