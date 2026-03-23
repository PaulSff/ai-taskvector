"""
Tests for semantics LanguageDetector unit and detect_language_for_prompt().

Run from repo root:
  pytest units/semantics/language_detector/tests/test_language_detector.py -v
  python units/semantics/language_detector/tests/test_language_detector.py

Requires lingua-language-detector for tests that call Lingua (skipped automatically if missing).
"""
from __future__ import annotations

import sys
from pathlib import Path

# tests/ -> language_detector/ -> semantics/ -> units/ -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _register_language_detector() -> None:
    from units.semantics.language_detector.language_detector import register_language_detector

    register_language_detector()


def _get_spec(type_name: str):
    from units.registry import get_unit_spec

    return get_unit_spec(type_name)


def _lingua_installed() -> bool:
    try:
        import lingua  # noqa: F401
        return True
    except ImportError:
        return False


# ---- detect_language_for_prompt ----


def test_detect_language_for_prompt_empty_uses_default_iso() -> None:
    from units.semantics.language_detector.language_detector import detect_language_for_prompt

    iso, hint = detect_language_for_prompt("", default_iso="fr")
    assert iso == "fr"
    assert "fr" in hint.lower() or "(" in hint


def test_detect_language_for_prompt_whitespace_only_uses_default() -> None:
    from units.semantics.language_detector.language_detector import detect_language_for_prompt

    iso, hint = detect_language_for_prompt("   \n\t  ", default_iso="en")
    assert iso == "en"
    assert "English" in hint or "en" in hint


def test_detect_language_for_prompt_english_sentence() -> None:
    if not _lingua_installed():
        import pytest

        pytest.skip("lingua-language-detector not installed")
    from units.semantics.language_detector.language_detector import detect_language_for_prompt

    iso, hint = detect_language_for_prompt(
        "The quick brown fox jumps over the lazy dog.",
        languages_csv="en,de,fr",
    )
    assert iso == "en"
    assert "en" in hint.lower()


def test_detect_language_for_prompt_german_sentence() -> None:
    if not _lingua_installed():
        import pytest

        pytest.skip("lingua-language-detector not installed")
    from units.semantics.language_detector.language_detector import detect_language_for_prompt

    iso, hint = detect_language_for_prompt(
        "Guten Tag, ich möchte einen Workflow erstellen und die Einheiten verbinden.",
        languages_csv="en,de,fr",
    )
    assert iso == "de"
    assert "de" in hint.lower()


# ---- LanguageDetector unit step_fn ----


def test_language_detector_spec_registered() -> None:
    _register_language_detector()
    spec = _get_spec("LanguageDetector")
    assert spec is not None
    assert spec.type_name == "LanguageDetector"
    assert spec.step_fn is not None
    assert len(spec.input_ports) >= 1
    assert any(p[0] == "text" for p in spec.input_ports)


def test_step_empty_text_returns_default_when_unknown() -> None:
    _register_language_detector()
    spec = _get_spec("LanguageDetector")
    assert spec and spec.step_fn
    outputs, _ = spec.step_fn(
        {"default_when_unknown": "en"},
        {"text": ""},
        {},
        0.0,
    )
    assert outputs["iso639_1"] == "en"
    assert outputs["confidence"] == 0.0
    assert outputs["error"] is None


def test_step_text_from_params_when_input_missing() -> None:
    """When input port 'text' is absent, step uses params.text (agent-style)."""
    if not _lingua_installed():
        import pytest

        pytest.skip("lingua-language-detector not installed")
    _register_language_detector()
    spec = _get_spec("LanguageDetector")
    assert spec and spec.step_fn
    outputs, _ = spec.step_fn(
        {"languages": "en,de", "default_when_unknown": "fr", "text": "Short English phrase for testing."},
        {},
        {},
        0.0,
    )
    assert outputs.get("error") is None
    assert outputs["iso639_1"] == "en"


def test_step_english_when_lingua_installed() -> None:
    if not _lingua_installed():
        import pytest

        pytest.skip("lingua-language-detector not installed")
    _register_language_detector()
    spec = _get_spec("LanguageDetector")
    assert spec and spec.step_fn
    outputs, _ = spec.step_fn(
        {"languages": "en,de,fr", "default_when_unknown": "en"},
        {"text": "Hello, please add a unit to the graph."},
        {},
        0.0,
    )
    assert outputs.get("error") is None
    assert outputs["iso639_1"] == "en"
    assert outputs["confidence"] > 0.0
    assert outputs["reliable"] is True


def test_step_german_when_lingua_installed() -> None:
    if not _lingua_installed():
        import pytest

        pytest.skip("lingua-language-detector not installed")
    _register_language_detector()
    spec = _get_spec("LanguageDetector")
    assert spec and spec.step_fn
    outputs, _ = spec.step_fn(
        {"languages": "en,de,fr", "default_when_unknown": "en"},
        {"text": "Bitte verbinde die beiden Knoten im Diagramm."},
        {},
        0.0,
    )
    assert outputs.get("error") is None
    assert outputs["iso639_1"] == "de"
    assert outputs["language"]  # Lingua enum name, e.g. GERMAN


def test_step_min_confidence_forces_default() -> None:
    if not _lingua_installed():
        import pytest

        pytest.skip("lingua-language-detector not installed")
    _register_language_detector()
    spec = _get_spec("LanguageDetector")
    assert spec and spec.step_fn
    outputs, _ = spec.step_fn(
        {
            "languages": "en,de",
            "default_when_unknown": "en",
            "min_confidence": 0.99999,
        },
        {"text": "Hello world"},
        {},
        0.0,
    )
    assert outputs["iso639_1"] == "en"
    assert outputs["reliable"] is False


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
