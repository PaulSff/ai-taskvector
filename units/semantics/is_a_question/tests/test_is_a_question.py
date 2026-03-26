"""
Tests for semantics IsAQuestion unit.

Run from repo root:
  pytest units/semantics/is_a_question/tests/test_is_a_question.py -v
  python units/semantics/is_a_question/tests/test_is_a_question.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# tests/ -> is_a_question/ -> semantics/ -> units/ -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _register_is_a_question() -> None:
    from units.semantics.is_a_question.is_a_question import register_is_a_question

    register_is_a_question()


def _get_spec(type_name: str):
    from units.registry import get_unit_spec

    return get_unit_spec(type_name)


def test_is_a_question_spec_registered() -> None:
    _register_is_a_question()
    spec = _get_spec("IsAQuestion")
    assert spec is not None
    assert spec.type_name == "IsAQuestion"
    assert spec.step_fn is not None
    assert any(p[0] == "text" for p in spec.input_ports)
    assert any(p[0] == "is_question" for p in spec.output_ports)
    assert any(p[0] == "question_sentence" for p in spec.output_ports)
    assert any(p[0] == "non_question_text" for p in spec.output_ports)


def test_returns_true_and_first_question_sentence() -> None:
    _register_is_a_question()
    spec = _get_spec("IsAQuestion")
    assert spec and spec.step_fn
    text = "Hello there. How are you? I am fine."
    out, _ = spec.step_fn({}, {"text": text}, {}, 0.0)
    assert out.get("is_question") is True
    assert out.get("question_sentence") == "How are you?"
    assert out.get("non_question_text") == ""


def test_returns_false_when_no_question() -> None:
    _register_is_a_question()
    spec = _get_spec("IsAQuestion")
    assert spec and spec.step_fn
    text = "Hello there. This is a statement."
    out, _ = spec.step_fn({}, {"text": text}, {}, 0.0)
    assert out.get("is_question") is False
    assert out.get("question_sentence") == ""
    assert out.get("non_question_text") == text


def test_params_text_fallback() -> None:
    _register_is_a_question()
    spec = _get_spec("IsAQuestion")
    assert spec and spec.step_fn
    out, _ = spec.step_fn({"text": "Can this run from params?"}, {}, {}, 0.0)
    assert out.get("is_question") is True
    assert out.get("question_sentence") == "Can this run from params?"
    assert out.get("non_question_text") == ""


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
