"""Environment "discovery" units (scaffolded by list_environment). See README.md."""
from __future__ import annotations

import logging

from units.discovery.list_dir.list_dir import register_list_dir
from units.env_loaders import register_env_loader
from units.registry import UNIT_REGISTRY

logger = logging.getLogger(__name__)

_DISCOVERY_TYPE_NAMES = (
    "ListDir",
)

def register_discovery_units() -> None:
    """Register units for discovery. Add register_* calls as you add units under units/discovery/."""
    register_list_dir()

    for name in _DISCOVERY_TYPE_NAMES:
        spec = UNIT_REGISTRY.get(name)
        if spec is not None:
            spec.environment_tags = ["discovery"]


def _register_discovery_env_loader() -> None:
    try:
        from units.env_loaders import register_env_loader
    except ImportError:
        logger.info("env_loaders not available; cannot register network env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_env_loader for discovery")
        raise

    try:
        from units.discovery import register_discovery_units
    except ImportError:
        logger.info("units.network not available; cannot register discovery env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_discovery_units for discovery")
        raise

    try:
        register_env_loader("discovery", register_discovery_units)
    except Exception:
        logger.exception("Failed to register discovery env loader")
        raise

_register_discovery_env_loader()

register_env_loader("discovery", register_discovery_units)

__all__ = ["register_discovery_units"]
