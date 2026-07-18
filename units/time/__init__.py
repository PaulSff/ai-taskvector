"""Environment "time" units. See README.md."""
from __future__ import annotations

from units.registry import UNIT_REGISTRY
from units.env_loaders import register_env_loader
from units.time.calendar import (
    register_calendar_unit,
)


_TIME_TYPE_NAMES = (
    "CalendarICS",
)

for name in _TIME_TYPE_NAMES:
    spec = UNIT_REGISTRY.get(name)
    if spec is not None:
        spec.environment_tags = ["time"]



def register_time_units() -> None:
    """Register units for time. Add register_* calls as you add units under units/time/."""
    register_calendar_unit()
    pass


def _register_time_env_loader() -> None:
    try:
        register_env_loader("time", register_time_units)
    except Exception:
        pass

_register_time_env_loader()

__all__ = ["register_time_units"]
