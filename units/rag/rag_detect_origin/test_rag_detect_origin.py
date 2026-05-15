import json
from pathlib import Path

import pytest

# Adjust import path as needed to import the module under test
import units.rag.rag_detect_origin.rag_detect_origin as rdo


# A small fake classifier to avoid importing real registry behavior.
# Monkeypatch classify_content to return predictable origins for tests.
def fake_classify(disc_path, data):
    # Determine origin by presence of keys or scalar wrapping
    if data is None:
        return {"content_kind": "json-generic", "id": "json-generic"}
    if isinstance(data, dict):
        if data.get("type") == "example":
            return {"content_kind": "example-kind", "id": "example"}
        if "value" in data and len(data) == 1:
            return {"content_kind": "scalar-kind", "id": "scalar"}
        return {"content_kind": "dict-kind", "id": "dict"}
    if isinstance(data, list):
        return {"content_kind": "list-kind", "id": "list"}
    return {"content_kind": "json-generic", "id": "json-generic"}


@pytest.fixture(autouse=True)
def patch_classify(monkeypatch):
    monkeypatch.setattr(rdo, "classify_content", fake_classify)
    yield


def write_temp(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


def test_json_file(tmp_path):
    p = tmp_path / "g.json"
    write_temp(p, json.dumps({"type": "example"}))
    data, hint = rdo._graph_to_data(str(p))
    assert isinstance(data, dict)
    assert hint == p
    out, _ = rdo._rag_detect_origin_step({}, {"graph": str(p)}, {}, 0.0)
    assert out["origin"] == "example-kind"
    assert out["graph"] == {"type": "example"}


def test_yaml_file(tmp_path):
    p = tmp_path / "g.yaml"
    yaml_text = "type: example\n"
    write_temp(p, yaml_text)
    data, hint = rdo._graph_to_data(str(p))
    # If PyYAML installed, data should be dict; otherwise None (file exists but parser not available)
    if rdo.yaml is not None:
        assert isinstance(data, dict)
        out, _ = rdo._rag_detect_origin_step({}, {"graph": str(p)}, {}, 0.0)
        assert out["origin"] == "example-kind"
        assert out["graph"] == {"type": "example"}
    else:
        # Without PyYAML, parsing fails and classify will receive None -> generic
        out, _ = rdo._rag_detect_origin_step({}, {"graph": str(p)}, {}, 0.0)
        assert out["origin"] == "json-generic"


def test_json_string():
    s = json.dumps({"type": "example"})
    data, hint = rdo._graph_to_data(s)
    assert isinstance(data, dict)
    out, _ = rdo._rag_detect_origin_step({}, {"graph": s}, {}, 0.0)
    assert out["origin"] == "example-kind"


def test_yaml_string():
    s = "type: example\n"
    data, hint = rdo._graph_to_data(s)
    if rdo.yaml is not None:
        assert isinstance(data, dict)
        out, _ = rdo._rag_detect_origin_step({}, {"graph": s}, {}, 0.0)
        assert out["origin"] == "example-kind"
    else:
        out, _ = rdo._rag_detect_origin_step({}, {"graph": s}, {}, 0.0)
        # Without PyYAML, string won't parse as JSON; origin generic
        assert out["origin"] == "json-generic"


def test_bundle_with_parsed_dict():
    bundle = {"parsed": {"type": "example"}, "file_path": ""}
    data, hint = rdo._graph_to_data(bundle)
    assert isinstance(data, dict)
    out, _ = rdo._rag_detect_origin_step({}, {"graph": bundle}, {}, 0.0)
    assert out["origin"] == "example-kind"


def test_bundle_with_parsed_yaml_string():
    bundle = {"parsed": "type: example\n", "file_path": ""}
    data, hint = rdo._graph_to_data(bundle)
    if rdo.yaml is not None:
        assert isinstance(data, dict)
        out, _ = rdo._rag_detect_origin_step({}, {"graph": bundle}, {}, 0.0)
        assert out["origin"] == "example-kind"
    else:
        out, _ = rdo._rag_detect_origin_step({}, {"graph": bundle}, {}, 0.0)
        assert out["origin"] == "json-generic"


def test_scalar_yaml_wrap(tmp_path):
    p = tmp_path / "scalar.yaml"
    write_temp(p, "42\n")
    data, hint = rdo._graph_to_data(str(p))
    if rdo.yaml is not None:
        # Should wrap scalar into {"value": 42}
        assert isinstance(data, dict)
        assert data.get("value") == 42
        out, _ = rdo._rag_detect_origin_step({}, {"graph": str(p)}, {}, 0.0)
        assert out["origin"] == "scalar-kind"
    else:
        out, _ = rdo._rag_detect_origin_step({}, {"graph": str(p)}, {}, 0.0)
        assert out["origin"] == "json-generic"
