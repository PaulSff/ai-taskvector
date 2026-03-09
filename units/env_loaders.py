"""
Registry of environment unit loaders. Environment packages (thermodynamic, data_bi, etc.)
register their loader here; callers use this to ensure units are registered without hardcoding env names.
"""
from __future__ import annotations

from typing import Callable

# tag (e.g. "thermodynamic", "data_bi") -> no-arg callable that registers that env's units
_ENV_LOADERS: dict[str, Callable[[], None]] = {}


def _ensure_loaders_discovered() -> None:
    """Import env packages so they register their loaders. Add new env packages here."""
    try:
        import units.thermodynamic  # noqa: F401
    except Exception:
        pass
    try:
        import units.data_bi  # noqa: F401
    except Exception:
        pass
    try:
        import units.pyflow  # noqa: F401  # registers "pyflow" env loader
    except Exception:
        pass


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
            pass


def ensure_all_environment_units_registered() -> None:
    """Run all registered environment loaders. Use when the full unit list is needed (e.g. Units Library)."""
    _ensure_loaders_discovered()
    for loader in _ENV_LOADERS.values():
        try:
            loader()
        except Exception:
            pass
