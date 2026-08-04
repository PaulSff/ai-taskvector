"""Environment "network" units (scaffolded by list_environment). See README.md."""
from __future__ import annotations

import logging

from units.env_loaders import register_env_loader
from units.network.http_in import register_http_in
from units.network.http_response import register_http_response
from units.network.mcp_source.mcp_source import register_mcp_source
from units.network.mcp_tool import register_mcp_tool
from units.registry import UNIT_REGISTRY

logger = logging.getLogger(__name__)

_NETWORK_TYPE_NAMES = (
    "MCPTool",
    "MCPSource",
    "HttpResponse",
    "HttpIn",
)


def register_network_units() -> None:
    """Register units for network. Add register_* calls as you add units under units/network/."""
    register_http_in()
    register_http_response()
    register_mcp_tool()
    register_mcp_source()
    for name in _NETWORK_TYPE_NAMES:
        spec = UNIT_REGISTRY.get(name)
        if spec is not None:
            spec.environment_tags = ["network"]


def _register_network_env_loader() -> None:
    try:
        from units.env_loaders import register_env_loader
    except ImportError:
        logger.info("env_loaders not available; cannot register network env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_env_loader for network")
        raise

    try:
        from units.network import register_network_units
    except ImportError:
        logger.info("units.network not available; cannot register network env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_network_units for network")
        raise

    try:
        register_env_loader("network", register_network_units)
    except Exception:
        logger.exception("Failed to register network env loader")
        raise

_register_network_env_loader()

register_env_loader("network", register_network_units)

__all__ = ["register_network_units"]
