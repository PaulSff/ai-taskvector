"""Canonical training flow units: Join, Merge, Prompt, Split, Switch, StepDriver, StepRewards, HttpIn, HttpResponse, Random. (function lives in units/env_agnostic as env-agnostic; browser/web_search live in units/web.)"""

from units.canonical.http_in import register_http_in
from units.pyflow import register_pyflow_units
from units.canonical.http_response import register_http_response
from units.canonical.join import register_join
from units.canonical.merge import register_merge
from units.canonical.prompt import register_prompt
from units.canonical.random import register_random
from units.canonical.split import register_split
from units.canonical.step_driver import register_step_driver
from units.canonical.step_rewards import register_step_rewards
from units.canonical.switch import register_switch


def register_canonical_units() -> None:
    """Register Split, Join, Merge, Prompt, Switch, StepDriver, StepRewards, HttpIn, HttpResponse, Random for canonical graph topology."""
    from units.registry import UNIT_REGISTRY

    register_split()
    register_join()
    register_merge()
    register_prompt()
    register_switch()
    register_step_driver()
    register_step_rewards()
    register_http_in()
    register_http_response()
    register_random()
    register_pyflow_units()  # also registered as env "pyflow" loader for filtering
    canonical_type_names = (
        "Join", "Merge", "Prompt", "Split", "Switch", "StepDriver", "StepRewards", "HttpIn", "HttpResponse", "Random",
    )
    for name in canonical_type_names:
        spec = UNIT_REGISTRY.get(name)
        if spec is not None:
            spec.environment_tags = ["canonical"]
            spec.environment_tags_are_agnostic = True
            spec.runtime_scope = "canonical"


__all__ = ["register_canonical_units"]
