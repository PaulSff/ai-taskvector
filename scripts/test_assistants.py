"""
Test assistant apply: graph edits via ApplyEdits + NormalizeGraph workflows; training via ApplyTrainingConfigEdits.
Core graph_edit tests still use apply_graph_edit directly.

Run from repo root: python scripts/test_assistants.py
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.normalizer import load_process_graph_from_file, load_training_config_from_file
from core.graph.graph_edits import apply_graph_edit
from core.schemas.process_graph import ProcessGraph
from core.schemas.training_config import TrainingConfig
from gui.components.workflow_tab.workflows.core_workflows import (
    register_env_agnostic_units,
    run_apply_edits,
    run_apply_training_config_edits,
    run_normalize_graph,
)


def _apply_graph_edits_workflow(graph: ProcessGraph, edit: dict) -> ProcessGraph:
    """ApplyEdits (batch) + NormalizeGraph — same units as Workflow Designer apply step."""
    register_env_agnostic_units()
    updated, err = run_apply_edits(graph, [edit])
    if err:
        raise AssertionError(err)
    gdict = updated if isinstance(updated, dict) else graph.model_dump(by_alias=True)
    normalized, norm_err = run_normalize_graph(gdict)
    if norm_err:
        raise AssertionError(norm_err)
    assert normalized is not None
    return ProcessGraph.model_validate(normalized)


def _apply_training_edits_workflow(config: TrainingConfig, edit: dict) -> TrainingConfig:
    """ApplyTrainingConfigEdits — same unit as rl_coach_workflow apply step."""
    register_env_agnostic_units()
    out, err = run_apply_training_config_edits(config, [edit])
    if err:
        raise AssertionError(err)
    assert out is not None
    return TrainingConfig.model_validate(out)


def test_process_assistant_no_edit():
    base = REPO_ROOT / "config" / "examples" / "temperature_process.yaml"
    graph = load_process_graph_from_file(base)
    edit = {"action": "no_edit", "reason": "no change"}
    result = _apply_graph_edits_workflow(graph, edit)
    assert result.environment_type.value == "thermodynamic"
    assert len(result.units) == len(graph.units)
    assert len(result.connections) == len(graph.connections)


def test_process_assistant_add_unit():
    base = REPO_ROOT / "config" / "examples" / "temperature_process.yaml"
    graph = load_process_graph_from_file(base)
    n_units = len(graph.units)
    edit = {
        "action": "add_unit",
        "unit": {
            "id": "extra_valve",
            "type": "Valve",
            "controllable": True,
            "params": {},
        },
    }
    result = _apply_graph_edits_workflow(graph, edit)
    assert len(result.units) == n_units + 1
    assert result.get_unit("extra_valve") is not None
    assert result.get_unit("extra_valve").type == "Valve"


def test_process_assistant_connect():
    base = REPO_ROOT / "config" / "examples" / "temperature_process.yaml"
    graph = load_process_graph_from_file(base)
    n_conn = len(graph.connections)
    edit = {"action": "connect", "from": "hot_source", "to": "cold_valve"}
    result = _apply_graph_edits_workflow(graph, edit)
    assert len(result.connections) == n_conn + 1
    pairs = [(c.from_id, c.to_id) for c in result.connections]
    assert ("hot_source", "cold_valve") in pairs


def test_graph_edit_connect_rejects_duplicate_same_ports():
    """Same from/to and same ports must not be added twice."""
    current = {
        "units": [
            {"id": "u1", "type": "Source", "controllable": False, "params": {}},
            {"id": "u2", "type": "Valve", "controllable": True, "params": {}},
        ],
        "connections": [{"from": "u1", "to": "u2", "from_port": "0", "to_port": "0"}],
    }
    edit = {"action": "connect", "from": "u1", "to": "u2", "from_port": "0", "to_port": "0"}
    try:
        apply_graph_edit(current, edit)
    except ValueError as e:
        assert "uplicate" in str(e)
    else:
        raise AssertionError("expected ValueError for duplicate connection")


def test_graph_edit_connect_allows_same_units_different_ports():
    """Same endpoints with different ports are distinct edges."""
    current = {
        "units": [
            {"id": "u1", "type": "Source", "controllable": False, "params": {}},
            {"id": "u2", "type": "Valve", "controllable": True, "params": {}},
        ],
        "connections": [{"from": "u1", "to": "u2", "from_port": "0", "to_port": "0"}],
    }
    edit = {"action": "connect", "from": "u1", "to": "u2", "from_port": "0", "to_port": "1"}
    out = apply_graph_edit(current, edit)
    conns = out.get("connections") or []
    assert len(conns) == 2


def test_graph_edit_replace_graph_rejects_duplicate_connections():
    """replace_graph must not contain two identical (from, to, from_port, to_port) edges."""
    edit = {
        "action": "replace_graph",
        "units": [
            {"id": "a", "type": "Source", "controllable": False, "params": {}},
            {"id": "b", "type": "Valve", "controllable": True, "params": {}},
        ],
        "connections": [
            {"from": "a", "to": "b", "from_port": "0", "to_port": "0"},
            {"from": "a", "to": "b", "from_port": "0", "to_port": "0"},
        ],
    }
    try:
        apply_graph_edit({"units": [], "connections": []}, edit)
    except ValueError as e:
        assert "uplicate" in str(e)
    else:
        raise AssertionError("expected ValueError for duplicate connection in replace_graph")


def test_graph_edit_replace_graph_allows_same_units_different_ports():
    """Same unit pair with different ports is valid in replace_graph."""
    edit = {
        "action": "replace_graph",
        "units": [
            {"id": "a", "type": "Source", "controllable": False, "params": {}},
            {"id": "b", "type": "Valve", "controllable": True, "params": {}},
        ],
        "connections": [
            {"from": "a", "to": "b", "from_port": "0", "to_port": "0"},
            {"from": "a", "to": "b", "from_port": "0", "to_port": "1"},
        ],
    }
    out = apply_graph_edit({"units": [], "connections": []}, edit)
    assert len(out.get("connections") or []) == 2


def test_process_assistant_connect_with_ports():
    """Connect with explicit from_port and to_port; verify they are stored on the connection."""
    base = REPO_ROOT / "config" / "examples" / "temperature_process.yaml"
    graph = load_process_graph_from_file(base)
    edit = {
        "action": "connect",
        "from": "hot_source",
        "to": "cold_valve",
        "from_port": "1",
        "to_port": "0",
    }
    result = _apply_graph_edits_workflow(graph, edit)
    conn = next(
        (c for c in result.connections if c.from_id == "hot_source" and c.to_id == "cold_valve"),
        None,
    )
    assert conn is not None, "Expected connection hot_source -> cold_valve"
    assert conn.from_port == "1", f"Expected from_port '1', got {conn.from_port!r}"
    assert conn.to_port == "0", f"Expected to_port '0', got {conn.to_port!r}"


def test_apply_training_config_edits_workflow_no_edit():
    base = REPO_ROOT / "config" / "examples" / "training_config.yaml"
    config = load_training_config_from_file(base)
    edit = {"action": "no_edit", "reason": "no change"}
    result = _apply_training_edits_workflow(config, edit)
    assert result.goal.target_temp == config.goal.target_temp
    assert result.hyperparameters.learning_rate == config.hyperparameters.learning_rate


def test_apply_training_config_edits_workflow_merge():
    base = REPO_ROOT / "config" / "examples" / "training_config.yaml"
    config = load_training_config_from_file(base)
    edit = {"rewards": {"weights": {"dumping": -0.2}}}
    result = _apply_training_edits_workflow(config, edit)
    assert result.rewards.weights["dumping"] == -0.2
    assert result.goal.target_temp == config.goal.target_temp


if __name__ == "__main__":
    test_process_assistant_no_edit()
    test_process_assistant_add_unit()
    test_process_assistant_connect()
    test_graph_edit_connect_rejects_duplicate_same_ports()
    test_graph_edit_connect_allows_same_units_different_ports()
    test_graph_edit_replace_graph_rejects_duplicate_connections()
    test_graph_edit_replace_graph_allows_same_units_different_ports()
    test_process_assistant_connect_with_ports()
    test_apply_training_config_edits_workflow_no_edit()
    test_apply_training_config_edits_workflow_merge()
    print("All assistant tests passed.")
