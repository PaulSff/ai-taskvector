"""Canonical training flow units: Split, Join, Switch, StepDriver, StepRewards, HttpIn, HttpResponse."""

from units.canonical.http_in import register_http_in
from units.canonical.http_response import register_http_response
from units.canonical.join import register_join
from units.canonical.split import register_split
from units.canonical.step_driver import register_step_driver
from units.canonical.step_rewards import register_step_rewards
from units.canonical.switch import register_switch


def register_canonical_units() -> None:
    """Register Split, Join, Switch, StepDriver, StepRewards, HttpIn, HttpResponse for canonical graph topology."""
    register_split()
    register_join()
    register_switch()
    register_step_driver()
    register_step_rewards()
    register_http_in()
    register_http_response()


__all__ = ["register_canonical_units"]
