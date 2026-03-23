"""
LanguageDetector unit: detect natural language of input text using lingua (offline).

Requires: pip install lingua-language-detector (see units/semantics/requirements.txt).

Params:
  - languages: comma-separated ISO 639-1 codes to consider, e.g. "en,de,fr". Empty or "all"
    uses all spoken languages supported by Lingua (heavier). Restricting improves speed/accuracy.
  - low_accuracy: if true, use Lingua low-accuracy mode (faster, worse on short text).
  - min_confidence: 0.0–1.0; if the top language confidence is below this, output iso639_1
    is set to default_when_unknown instead.
  - default_when_unknown: ISO 639-1 string when detection fails or is uncertain (default "").

Input: text (str) — optional; can also pass via params.text for agent-style use.
Outputs: iso639_1 (lowercase, e.g. "de"), confidence (float), language (str, Lingua enum name),
  reliable (bool), error (str | None).
"""
from __future__ import annotations

import functools
from typing import Any

from units.registry import UnitSpec, register_unit

# Default: empty / "all" → from_all_spoken_languages() (all languages Lingua supports; matches assistant_workflow).
DEFAULT_LANGUAGES_PARAM = ""


def detect_language_for_prompt(
    text: str,
    *,
    default_iso: str = "en",
    languages_csv: str = DEFAULT_LANGUAGES_PARAM,
) -> tuple[str, str]:
    """
    Detect ISO 639-1 code and a short hint for prompts/inject strings.
    Matches LanguageDetector unit logic so Merge→Prompt and Python-built injects stay aligned.
    Returns (iso639_1, hint) where hint is like 'German (de)' or 'English (en)'.
    When lingua is missing or text is empty, returns (default_iso, English-style hint).
    """
    raw = _normalize_text(text)
    if not raw:
        return default_iso, _default_language_hint(default_iso)

    lang_spec = str(languages_csv).strip().lower()
    if not lang_spec or lang_spec in ("all", "all_spoken", "*"):
        cache_key = "all_spoken"
    else:
        parts = sorted({p.strip().lower() for p in str(languages_csv).split(",") if p.strip()})
        cache_key = ",".join(parts) if parts else "all_spoken"

    try:
        detector = _build_lingua_detector(cache_key, False)
    except ImportError:
        return default_iso, _default_language_hint(default_iso)

    try:
        detected = detector.detect_language_of(raw)
        if detected is None:
            return default_iso, _default_language_hint(default_iso)
        iso = detected.iso_code_639_1
        iso_str = iso.name.lower() if iso is not None else default_iso
        lingua_name = getattr(detected, "name", "") or ""
        nice = lingua_name.replace("_", " ").title() if lingua_name else ""
        hint = f"{nice} ({iso_str})" if nice else _default_language_hint(iso_str)
        return iso_str, hint
    except Exception:
        return default_iso, _default_language_hint(default_iso)


def _default_language_hint(iso: str) -> str:
    low = (iso or "en").strip().lower() or "en"
    if low == "en":
        return "English (en)"
    return f"({low})"


INPUT_PORTS = [("text", "str")]
OUTPUT_PORTS = [
    ("iso639_1", "str"),
    ("confidence", "float"),
    ("language", "str"),
    ("reliable", "Any"),
    ("error", "str"),
]


def _normalize_text(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        try:
            return raw.decode("utf-8", errors="replace").strip()
        except Exception:
            return ""
    return str(raw).strip()


def _iter_lingua_languages(Language: Any) -> list[Any]:
    """Language.all may be a callable or an iterable depending on lingua version."""
    all_attr = getattr(Language, "all", None)
    if all_attr is None:
        return []
    if callable(all_attr):
        return list(all_attr())
    return list(all_attr)


@functools.lru_cache(maxsize=16)
def _build_lingua_detector(lang_key: str, low_accuracy: bool) -> Any:
    """lang_key: 'all_spoken' or comma-sorted lower ISO codes e.g. 'de,en,fr'."""
    from lingua import Language, LanguageDetectorBuilder

    builder: Any
    if lang_key == "all_spoken":
        builder = LanguageDetectorBuilder.from_all_spoken_languages()
    else:
        want = {c.strip().lower() for c in lang_key.split(",") if c.strip()}
        langs: list[Any] = []
        for lang in _iter_lingua_languages(Language):
            iso = lang.iso_code_639_1
            if iso is not None and iso.name.lower() in want:
                langs.append(lang)
        if not langs:
            builder = LanguageDetectorBuilder.from_all_spoken_languages()
        else:
            builder = LanguageDetectorBuilder.from_languages(*langs)
    if low_accuracy:
        builder = builder.with_low_accuracy_mode()
    return builder.build()


def _language_detector_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    par = params or {}
    text = _normalize_text(inputs.get("text") if inputs else None)
    if not text:
        text = _normalize_text(par.get("text"))

    langs_raw = par.get("languages")
    if langs_raw is None:
        langs_raw = ""
    low_acc = bool(par.get("low_accuracy") or par.get("lowAccuracy"))
    try:
        min_conf = float(par.get("min_confidence", par.get("minConfidence", 0.0)))
    except (TypeError, ValueError):
        min_conf = 0.0
    min_conf = max(0.0, min(1.0, min_conf))
    default_unk = par.get("default_when_unknown", par.get("default_iso639_1", ""))
    if default_unk is not None and not isinstance(default_unk, str):
        default_unk = str(default_unk)
    default_unk = (default_unk or "").strip().lower()

    if not text:
        return (
            {
                "iso639_1": default_unk,
                "confidence": 0.0,
                "language": "",
                "reliable": False,
                "error": None,
            },
            state,
        )

    lang_spec = str(langs_raw).strip().lower()
    if not lang_spec or lang_spec in ("all", "all_spoken", "*"):
        cache_key = "all_spoken"
    else:
        parts = sorted({p.strip().lower() for p in str(langs_raw).split(",") if p.strip()})
        cache_key = ",".join(parts) if parts else "all_spoken"

    try:
        detector = _build_lingua_detector(cache_key, low_acc)
    except ImportError:
        return (
            {
                "iso639_1": default_unk,
                "confidence": 0.0,
                "language": "",
                "reliable": False,
                "error": "lingua-language-detector is not installed (pip install -r units/semantics/requirements.txt)",
            },
            state,
        )

    try:
        detected = detector.detect_language_of(text)
        confidences = detector.compute_language_confidence_values(text)
        top_conf = float(confidences[0].value) if confidences else 0.0
        reliable = bool(top_conf >= min_conf and detected is not None)

        if detected is None or top_conf < min_conf:
            return (
                {
                    "iso639_1": default_unk,
                    "confidence": top_conf,
                    "language": "",
                    "reliable": False,
                    "error": None,
                },
                state,
            )

        iso = detected.iso_code_639_1
        iso_str = iso.name.lower() if iso is not None else default_unk
        return (
            {
                "iso639_1": iso_str,
                "confidence": top_conf,
                "language": detected.name,
                "reliable": reliable,
                "error": None,
            },
            state,
        )
    except Exception as e:  # noqa: BLE001 — surface as error port for graph debugging
        msg = str(e)[:500]
        return (
            {
                "iso639_1": default_unk,
                "confidence": 0.0,
                "language": "",
                "reliable": False,
                "error": msg or "language detection failed",
            },
            state,
        )


def register_language_detector() -> None:
    register_unit(
        UnitSpec(
            type_name="LanguageDetector",
            input_ports=INPUT_PORTS,
            output_ports=OUTPUT_PORTS,
            step_fn=_language_detector_step,
            environment_tags=["semantics"],
            environment_tags_are_agnostic=False,
            runtime_scope=None,
            description=(
                "Detect language of text (lingua). Input: text. Params: languages (ISO codes, "
                "comma-separated or all), min_confidence, default_when_unknown, low_accuracy. "
                "Outputs: iso639_1, confidence, language, reliable, error."
            ),
        )
    )


__all__ = [
    "DEFAULT_LANGUAGES_PARAM",
    "INPUT_PORTS",
    "OUTPUT_PORTS",
    "detect_language_for_prompt",
    "register_language_detector",
]
