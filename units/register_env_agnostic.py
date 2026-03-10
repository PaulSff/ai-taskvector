"""
Environment-agnostic unit registration.

Canonical units (Join, Switch, StepDriver, Split, StepRewards, HttpIn, HttpResponse,
Random) and policy/gym types (RLAgent, LLMAgent, RLOracle, RLGym)
are available for all environments across the system — thermodynamics, data_bi, and any
future env. Register them once so every graph env and graph_edits can use them.
"""
from __future__ import annotations

_registered: bool = False


def register_env_agnostic_units() -> None:
    """Register canonical + StepDriver, StepRewards (any runtime) + function, exec, agents, pipelines. Idempotent."""
    global _registered
    if _registered:
        return
    from units.canonical import register_canonical_units
    from units.env_agnostic.function import register_function
    from units.env_agnostic.exec import register_exec
    from units.env_agnostic.agents import register_all_agents
    from units.env_agnostic.step_driver import register_step_driver
    from units.env_agnostic.step_rewards import register_step_rewards
    from units.pipelines import register_all_pipelines

    register_canonical_units()  # training flow + Inject, ApplyEdits, ProcessAgent, grep, trigger, graph_edit
    register_step_driver()   # any runtime (Node-RED, n8n, PyFlow, canonical)
    register_step_rewards()  # any runtime
    register_function()
    register_exec()
    register_all_agents()
    register_all_pipelines()
    _registered = True


__all__ = ["register_env_agnostic_units"]
