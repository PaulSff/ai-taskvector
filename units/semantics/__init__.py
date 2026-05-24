"""Semantics environment units: language detection and related NLP helpers."""

from __future__ import annotations

from units.env_loaders import register_env_loader

_registered = False


def register_semantics_units() -> None:
    """Register all semantics-tagged units (idempotent)."""
    global _registered
    if _registered:
        return
    from units.semantics.clean_text import register_clean_text
    from units.semantics.is_a_question import register_is_a_question
    from units.semantics.language_detector import register_language_detector
    from units.semantics.spacy_nlp_processor import register_spacy_nlp_processor

    register_language_detector()
    register_clean_text()
    register_is_a_question()
    register_spacy_nlp_processor()
    _registered = True


register_env_loader("semantics", register_semantics_units)

__all__ = ["register_semantics_units"]
