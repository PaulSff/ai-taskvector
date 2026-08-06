"""Environment "office" units (scaffolded by list_environment). See README.md."""
from __future__ import annotations

import logging

from units.env_loaders import register_env_loader
from units.office.report import register_report
from units.registry import UNIT_REGISTRY

_OFFICE_TYPE_NAMES = (
    "Report",
)

logger = logging.getLogger(__name__)

def register_office_units() -> None:
    """Register units for office. Add register_* calls as you add units under units/office/."""
    register_report()

    for name in _OFFICE_TYPE_NAMES:
        spec = UNIT_REGISTRY.get(name)
        if spec is not None:
            spec.environment_tags = ["office"]


def _register_office_env_loader() -> None:
    try:
        from units.env_loaders import register_env_loader
    except ImportError:
        logger.info("env_loaders not available; cannot register office env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_env_loader for office")
        raise

    try:
        from units.office import register_office_units
    except ImportError:
        logger.info("units.office not available; cannot register office env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_office_units for office")
        raise

    try:
        register_env_loader("office", register_office_units)
    except Exception:
        logger.exception("Failed to register office env loader")
        raise

_register_office_env_loader()


register_env_loader("office", register_office_units)

__all__ = ["register_office_units"]
