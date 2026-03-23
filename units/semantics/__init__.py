"""Semantics environment units: language detection and related NLP helpers."""

from __future__ import annotations

_registered = False


def register_semantics_units() -> None:
    """Register all semantics-tagged units (idempotent)."""
    global _registered
    if _registered:
        return
    from units.semantics.language_detector import register_language_detector

    register_language_detector()
    _registered = True


from units.env_loaders import register_env_loader

register_env_loader("semantics", register_semantics_units)

__all__ = ["register_semantics_units"]
