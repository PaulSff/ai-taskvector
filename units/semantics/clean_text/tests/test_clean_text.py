"""
Tests for semantics CleanText unit.

Run from repo root:
  pytest units/semantics/clean_text/tests/test_clean_text.py -v
  python units/semantics/clean_text/tests/test_clean_text.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# tests/ -> clean_text/ -> semantics/ -> units/ -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _register_clean_text() -> None:
    from units.semantics.clean_text.clean_text import register_clean_text

    register_clean_text()


def _get_spec(type_name: str):
    from units.registry import get_unit_spec

    return get_unit_spec(type_name)


def test_clean_text_spec_registered() -> None:
    _register_clean_text()
    spec = _get_spec("CleanText")
    assert spec is not None
    assert spec.type_name == "CleanText"
    assert spec.step_fn is not None
    assert any(p[0] == "text" for p in spec.input_ports)
    assert any(p[0] == "error" for p in spec.output_ports)


def test_clean_text_removes_fenced_code() -> None:
    _register_clean_text()
    spec = _get_spec("CleanText")
    assert spec and spec.step_fn
    raw = """Need a workflow.

```python
def foo():
    return 1
```

Please keep only this text.
"""
    out, _ = spec.step_fn({}, {"text": raw}, {}, 0.0)
    txt = (out.get("text") or "").lower()
    assert "def foo" not in txt
    assert "please keep only this text" in txt
    assert out.get("error") in (None, "")


def test_clean_text_mixed_german_and_json_keeps_nl_drops_json_noise() -> None:
    _register_clean_text()
    spec = _get_spec("CleanText")
    assert spec and spec.step_fn
    raw = """Hallo, ich muss Flugangebote verarbeiten.
JSON-Beispiel:
"price": {
  "currency": "USD",
  "total": "2778.98"
},
"pricingOptions": { "includedCheckedBagsOnly": true }
"""
    out, _ = spec.step_fn(
        {"max_chars": 1000, "symbol_density_threshold": 0.25},
        {"text": raw},
        {},
        0.0,
    )
    txt = out.get("text") or ""
    # Keep natural-language German context
    assert "Hallo" in txt
    # Remove typical JSON key/value noise
    assert '"currency"' not in txt
    assert '"pricingOptions"' not in txt


def test_clean_text_respects_max_chars() -> None:
    _register_clean_text()
    spec = _get_spec("CleanText")
    assert spec and spec.step_fn
    raw = "This is a long sentence. " * 50
    out, _ = spec.step_fn({"max_chars": 40}, {"text": raw}, {}, 0.0)
    txt = out.get("text") or ""
    assert len(txt) <= 40


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
