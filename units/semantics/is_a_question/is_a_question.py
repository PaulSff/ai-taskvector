"""
IsAQuestion unit: detect whether input text contains a sentence ending with '?'.

Typical flow:
Inject(user_message) -> CleanText -> IsAQuestion -> branching logic
"""
from __future__ import annotations

import re
from typing import Any

from units.registry import UnitSpec, register_unit

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _normalize_text(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return ""
    return str(raw)


def _iter_sentences(text: str) -> list[str]:
    s = (text or "").strip()
    if not s:
        return []
    return [p.strip() for p in _SENTENCE_SPLIT_RE.split(s) if (p or "").strip()]


def _extract_question_sentence(text: str) -> str | None:
    for sent in _iter_sentences(text):
        if sent.rstrip().endswith("?"):
            return sent
    return None


def _is_a_question_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = _normalize_text((inputs or {}).get("text"))
    if not raw:
        raw = _normalize_text((params or {}).get("text"))
    try:
        sentence = _extract_question_sentence(raw)
        return (
            {
                "is_question": bool(sentence),
                "question_sentence": sentence or "",
                "non_question_text": "" if sentence else raw,
            },
            state,
        )
    except Exception as e:  # noqa: BLE001
        return (
            {
                "is_question": False,
                "question_sentence": "",
                "non_question_text": raw,
                "error": str(e)[:300] or "is_a_question failed",
            },
            state,
        )


def register_is_a_question() -> None:
    register_unit(
        UnitSpec(
            type_name="IsAQuestion",
            input_ports=[("text", "str")],
            output_ports=[
                ("is_question", "bool"),
                ("question_sentence", "str"),
                ("non_question_text", "str"),
            ],
            step_fn=_is_a_question_step,
            environment_tags=["semantics"],
            environment_tags_are_agnostic=False,
            runtime_scope=None,
            description=(
                "Detects whether input contains any sentence ending with '?'. "
                "Outputs a bool flag, the first matching question sentence, and passthrough text when false."
            ),
        )
    )


__all__ = ["register_is_a_question"]
