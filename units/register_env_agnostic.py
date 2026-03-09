"""
Environment-agnostic unit registration.

Canonical units (Join, Switch, StepDriver, Split, StepRewards, HttpIn, HttpResponse)
and policy/gym types (RLAgent, LLMAgent, RLOracle, RLGym) are available for all
environments across the system — thermodynamics, data_bi, and any future env.
Register them once so every graph env and graph_edits can use them.
"""
from __future__ import annotations

_registered: bool = False


def register_env_agnostic_units() -> None:
    """Register canonical + function (env-agnostic) + agents (RLAgent, LLMAgent) + pipelines (RLGym, RLOracle, RLSet, LLMSet). Idempotent; safe to call multiple times."""
    global _registered
    if _registered:
        return
    from units.canonical import register_canonical_units
    from units.env_agnostic.function import register_function
    from units.env_agnostic.exec import register_exec
    from units.env_agnostic.grep import register_grep
    from units.env_agnostic.agents import register_all_agents
    from units.pipelines import register_all_pipelines

    register_canonical_units()
    register_function()
    register_exec()
    register_grep()
    register_all_agents()
    register_all_pipelines()
    _registered = True


__all__ = ["register_env_agnostic_units"]
