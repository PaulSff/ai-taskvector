"""
Tests for auto-import flow: RagDetectOrigin, discriminant, Import_workflow, and full auto_import_workflow.

Run from repo root:
  PYTHONPATH=. python scripts/test_auto_import.py
  pytest scripts/test_auto_import.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _register_units() -> None:
    from units.register_env_agnostic import register_env_agnostic_units
    from units.canonical import register_canonical_units

    register_env_agnostic_units()
    register_canonical_units()


# ---- Discriminant (classify_json_for_rag) ----


def test_discriminant_canonical_dict_returns_canonical() -> None:
    """Canonical graph (units + connections, units have id/type) is classified as 'canonical'."""
    from rag.discriminant import classify_json_for_rag

    graph = {
        "units": [{"id": "u1", "type": "Inject", "params": {}}],
        "connections": [],
    }
    out = classify_json_for_rag(Path("."), graph)
    assert out == "canonical"


def test_discriminant_assistant_workflow_like_returns_canonical() -> None:
    """Real assistant_workflow-shaped dict is classified as canonical."""
    from rag.discriminant import classify_json_for_rag

    path = REPO_ROOT / "assistants" / "roles" / "workflow_designer" / "assistant_workflow.json"
    data = json.loads(path.read_text())
    out = classify_json_for_rag(Path("."), data)
    assert out == "canonical", f"expected canonical, got {out}"


def test_discriminant_node_red_returns_node_red() -> None:
    """Node-RED flow (nodes/flows or list of nodes) is classified as node_red."""
    from rag.discriminant import classify_json_for_rag

    data = {"nodes": [{"id": "n1", "type": "inject"}], "flows": []}
    out = classify_json_for_rag(Path("."), data)
    assert out == "node_red"


def test_discriminant_n8n_returns_n8n() -> None:
    """n8n (nodes list + connections dict) is classified as n8n."""
    from rag.discriminant import classify_json_for_rag

    data = {"nodes": [], "connections": {}}
    out = classify_json_for_rag(Path("."), data)
    assert out == "n8n"


# ---- RagDetectOrigin unit ----


def test_rag_detect_origin_canonical_dict_outputs_canonical() -> None:
    """RagDetectOrigin with canonical graph outputs origin='canonical', graph bypass, no error."""
    _register_units()
    from units.registry import get_unit_spec

    spec = get_unit_spec("RagDetectOrigin")
    assert spec is not None and spec.step_fn is not None

    graph = {
        "units": [{"id": "u1", "type": "Inject"}],
        "connections": [],
    }
    outputs, _ = spec.step_fn({}, {"graph": graph}, {}, 0.0)
    assert outputs["origin"] == "canonical"
    assert outputs["graph"] is graph
    assert outputs["error"] == ""


def test_rag_detect_origin_assistant_workflow_json() -> None:
    """RagDetectOrigin with assistant_workflow.json content returns origin canonical."""
    _register_units()
    from units.registry import get_unit_spec

    path = REPO_ROOT / "assistants" / "roles" / "workflow_designer" / "assistant_workflow.json"
    graph = json.loads(path.read_text())
    spec = get_unit_spec("RagDetectOrigin")
    assert spec is not None and spec.step_fn is not None

    outputs, _ = spec.step_fn({}, {"graph": graph}, {}, 0.0)
    assert outputs["origin"] == "canonical", f"origin={outputs['origin']!r} error={outputs['error']!r}"
    assert outputs["error"] == ""
    assert outputs["graph"] is graph


def test_rag_detect_origin_catalogue_mapped_to_generic() -> None:
    """Node-RED catalogue (modules list) is reported as generic, not node_red_catalogue."""
    _register_units()
    from units.registry import get_unit_spec

    spec = get_unit_spec("RagDetectOrigin")
    assert spec is not None and spec.step_fn is not None
    data = {"modules": [{"name": "foo", "version": "1.0"}]}
    outputs, _ = spec.step_fn({}, {"graph": data}, {}, 0.0)
    assert outputs["origin"] == "generic"
    assert outputs["error"] == ""


# ---- Import_workflow unit: canonical origin -> dict format ----


def test_import_workflow_canonical_origin_converts_to_process_graph() -> None:
    """Import_workflow with origin='canonical' and raw dict uses format 'dict' and succeeds."""
    _register_units()
    from units.registry import get_unit_spec

    spec = get_unit_spec("Import_workflow")
    assert spec is not None and spec.step_fn is not None

    graph = {
        "units": [
            {"id": "u1", "type": "Inject", "params": {}, "input_ports": [], "output_ports": [{"name": "data", "type": "Any"}]}
        ],
        "connections": [],
    }
    outputs, _ = spec.step_fn(
        {},
        {"graph": graph, "origin": "canonical"},
        {},
        0.0,
    )
    assert outputs["error"] == "", f"Import_workflow error: {outputs['error']}"
    assert outputs["graph"] is not None
    assert isinstance(outputs["graph"], dict)
    assert "units" in outputs["graph"]
    assert len(outputs["graph"]["units"]) == 1


def test_import_workflow_assistant_workflow_with_canonical_origin() -> None:
    """Full assistant_workflow.json with origin canonical converts successfully."""
    _register_units()
    from units.registry import get_unit_spec

    path = REPO_ROOT / "assistants" / "roles" / "workflow_designer" / "assistant_workflow.json"
    graph = json.loads(path.read_text())
    spec = get_unit_spec("Import_workflow")
    assert spec is not None and spec.step_fn is not None

    outputs, _ = spec.step_fn(
        {},
        {"graph": graph, "origin": "canonical"},
        {},
        0.0,
    )
    assert outputs["error"] == "", f"Import_workflow error: {outputs['error']}"
    assert outputs["graph"] is not None
    assert isinstance(outputs["graph"], dict)
    assert len(outputs["graph"].get("units", [])) > 1
    assert "connections" in outputs["graph"]


# ---- Full auto_import_workflow run ----


def test_auto_import_workflow_with_assistant_workflow_paste() -> None:
    """Run auto_import_workflow.json with pasted assistant_workflow JSON; expect canonical graph out."""
    _register_units()
    from runtime.run import run_workflow

    workflow_path = REPO_ROOT / "gui" / "flet" / "components" / "workflow" / "auto_import_workflow.json"
    if not workflow_path.is_file():
        raise FileNotFoundError(f"Missing {workflow_path}")

    with open(REPO_ROOT / "assistants" / "roles" / "workflow_designer" / "assistant_workflow.json") as f:
        raw_data = json.load(f)

    initial_inputs = {"inject_graph": {"data": raw_data}}
    outputs = run_workflow(str(workflow_path), initial_inputs=initial_inputs, format="dict")

    assert outputs is not None, "run_workflow returned None"
    iw = outputs.get("import_workflow") or {}
    err = iw.get("error") or ""
    graph = iw.get("graph")

    assert err == "", f"import_workflow error: {err}"
    assert graph is not None, "import_workflow did not return graph"
    assert isinstance(graph, dict), "graph is not a dict"
    assert "units" in graph, "graph has no units"
    assert len(graph["units"]) > 1, "expected multiple units from assistant_workflow"
    assert "connections" in graph


if __name__ == "__main__":
    _register_units()
    test_discriminant_canonical_dict_returns_canonical()
    test_discriminant_assistant_workflow_like_returns_canonical()
    test_discriminant_node_red_returns_node_red()
    test_discriminant_n8n_returns_n8n()
    test_rag_detect_origin_canonical_dict_outputs_canonical()
    test_rag_detect_origin_assistant_workflow_json()
    test_rag_detect_origin_catalogue_mapped_to_generic()
    test_import_workflow_canonical_origin_converts_to_process_graph()
    test_import_workflow_assistant_workflow_with_canonical_origin()
    test_auto_import_workflow_with_assistant_workflow_paste()
    print("All tests passed.")
