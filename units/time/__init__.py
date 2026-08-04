"""Environment "time" units. See README.md."""
from __future__ import annotations

import logging

from units.registry import UNIT_REGISTRY
from units.time.calendar import (
    register_calendar_unit,
)

logger = logging.getLogger(__name__)

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


def _register_time_env_loader() -> None:
    try:
        from units.env_loaders import register_env_loader
    except ImportError:
        logger.info("env_loaders not available; cannot register time env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_env_loader for time")
        raise

    try:
        from units.time import register_time_units
    except ImportError:
        logger.info("units.time not available; cannot register time env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_time_units for time")
        raise

    try:
        register_env_loader("time", register_time_units)
    except Exception:
        logger.exception("Failed to register time env loader")
        raise

_register_time_env_loader()

__all__ = ["register_time_units"]
