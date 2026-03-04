"""Canonical training flow units: Split, Join, Switch, StepDriver."""

from units.canonical.join import register_join
from units.canonical.split import register_split
from units.canonical.step_driver import register_step_driver
from units.canonical.switch import register_switch


def register_canonical_units() -> None:
    """Register Split, Join, Switch, StepDriver for canonical graph topology."""
    register_split()
    register_join()
    register_switch()
    register_step_driver()


__all__ = ["register_canonical_units"]
