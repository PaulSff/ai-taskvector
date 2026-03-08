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
    """Register canonical + RLAgent/LLMAgent/RLOracle/RLGym/RLSet/LLMSet. Idempotent; safe to call multiple times."""
    global _registered
    if _registered:
        return
    from units.canonical import register_canonical_units
    from units.agent import register_agent_units
    from units.oracle import register_oracle_units
    from units.rl_gym import register_rl_gym
    from units.pipeline import register_pipeline_units

    register_canonical_units()
    register_agent_units()
    register_oracle_units()
    register_rl_gym()
    register_pipeline_units()
    _registered = True


__all__ = ["register_env_agnostic_units"]
