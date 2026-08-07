"""
Registry of environment unit loaders. Environment packages (thermodynamic, data_bi, etc.)
register their loader here; callers use this to ensure units are registered without hardcoding env names.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

# tag (e.g. "thermodynamic", "data_bi") -> no-arg callable that registers that env's units
_ENV_LOADERS: dict[str, Callable[[], None]] = {}


def _ensure_loaders_discovered() -> None:
    """Import env packages so they register their loaders. Add new env packages here."""
    def _import_optional(module_name: str) -> None:
        try:
            __import__(module_name)
        except ModuleNotFoundError:
            # Package not installed / not present; optional, so skip.
            pass
        except Exception:
            # Real bug during import—surface it.
            logger.exception("Failed importing %s", module_name)
            raise

    _import_optional("units.thermodynamic")
    _import_optional("units.data_bi")
    _import_optional("units.pyflow")       # registers "pyflow" env loader
    _import_optional("units.node_red")    # registers "node_red" env loader
    _import_optional("units.n8n")         # registers "n8n" env loader
    _import_optional("units.web")         # registers "web" env loader
    _import_optional("units.messengers") # registers "messengers" env loader
    _import_optional("units.semantics")  # registers "semantics" env loader
    _import_optional("units.coding")  # registers "coding" env loader
    _import_optional("units.taskvector")  # registers "taskvector" env loader
    _import_optional("units.office")  # registers "office" env loader
    _import_optional("units.discovery")  # registers "discovery" env loader
    _import_optional("units.network")  # registers "network" env loader
    _import_optional("units.time")       # scaffolded by list_environment
    _import_optional("units.rag")        # registers "rag" env loader


def register_env_loader(tag: str, loader: Callable[[], None]) -> None:
    """Register a loader for the given environment tag. Called by units.thermodynamic, units.data_bi, etc."""
    t = str(tag).strip().lower()
    if t:
        _ENV_LOADERS[t] = loader


def known_environment_tags() -> list[str]:
    """Return sorted list of environment tags that have registered loaders."""
    _ensure_loaders_discovered()
    return sorted(_ENV_LOADERS.keys())


def ensure_environment_units_registered(tag: str) -> None:
    """Run the loader for the given environment tag if one is registered."""
    _ensure_loaders_discovered()
    t = str(tag).strip().lower()
    loader = _ENV_LOADERS.get(t)
    if loader is not None:
        try:
            loader()
        except Exception:
            logger.exception("Failed running environment loader for tag=%r", t)
            raise


def ensure_all_environment_units_registered() -> None:
    """Run all registered environment loaders. Use when the full unit list is needed (e.g. Units Library)."""
    _ensure_loaders_discovered()
    for loader in _ENV_LOADERS.values():
        try:
            loader()
        except Exception:
            logger.exception("Failed running environment loader: %r", loader)
            raise
