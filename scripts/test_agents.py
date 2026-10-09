"""
Test agent apply: graph edits via ApplyEdits + NormalizeGraph workflows; training via ApplyTrainingConfigEdits.
Core graph_edit tests still use apply_graph_edit directly.

Run from repo root: python scripts/test_agents.py
"""

import sys
from pathlib import Path

from core.graph.graph_edits import apply_graph_edit
from core.normalizer import load_process_graph_from_file, load_training_config_from_file
from core.schemas.graph_edit_api import GraphEdit
from core.schemas.process_graph import ProcessGraph
from core.schemas.training_config import TrainingConfig
from services.workflows.core_workflows import (
    register_env_agnostic_units,
    run_apply_edits,
    run_apply_training_config_edits,
    run_normalize_graph,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


async def _apply_graph_edits_workflow(
    graph: ProcessGraph,
    edit: GraphEdit
) -> ProcessGraph:
    """ApplyEdits (batch) + NormalizeGraph — same units as Workflow Designer apply step."""
    await register_env_agnostic_units()
    updated, err = await run_apply_edits(graph, [edit])
    if err:
        raise AssertionError(err)

    graph_to_normalize = (
        ProcessGraph.model_validate(updated)
        if isinstance(updated, dict)
        else updated
    )

    normalized, norm_err = await run_normalize_graph(graph_to_normalize)
    if norm_err:
        raise AssertionError(norm_err)
    assert normalized is not None
    return ProcessGraph.model_validate(normalized)


async def _apply_training_edits_workflow(
    config: TrainingConfig, edit: dict
) -> TrainingConfig:
    """ApplyTrainingConfigEdits — same unit as rl_coach_workflow apply step."""
    await register_env_agnostic_units()
    out, err = await run_apply_training_config_edits(config, [edit])
    if err:
        raise AssertionError(err)
    assert out is not None
    return TrainingConfig.model_validate(out)


async def test_process_agent_add_unit():
    base = REPO_ROOT / "config" / "examples" / "temperature_process.yaml"
    graph = load_process_graph_from_file(base)
    n_units = len(graph.units)
    edit = GraphEdit.model_validate({
        "action": "add_unit",
        "unit": {
            "id": "extra_valve",
            "type": "Valve",
            "controllable": True,
            "params": {},
        },
    })

    result = await _apply_graph_edits_workflow(graph, edit)
    assert len(result.units) == n_units + 1
    new_unit = result.get_unit("extra_valve")
    assert new_unit is not None
    assert new_unit.type == "Valve"


async def test_process_agent_connect():
    base = REPO_ROOT / "config" / "examples" / "temperature_process.yaml"
    graph = load_process_graph_from_file(base)
    n_conn = len(graph.connections)
    edit = GraphEdit.model_validate({
        "action": "connect",
        "from": "hot_source",
        "to": "cold_valve",
    })

    result = await _apply_graph_edits_workflow(graph, edit)
    assert len(result.connections) == n_conn + 1
    pairs = [(c.from_id, c.to_id) for c in result.connections]
    assert ("hot_source", "cold_valve") in pairs


def test_graph_edit_connect_rejects_duplicate_same_ports():
    """Same from/to and same ports must not be added twice."""
    current = ProcessGraph.model_validate({
        "units": [
            {"id": "u1", "type": "Source", "controllable": False, "params": {}},
            {"id": "u2", "type": "Valve", "controllable": True, "params": {}},
        ],
        "connections": [
            {"from": "u1", "to": "u2", "from_port": "0", "to_port": "0"}
        ],
    })
    edit = GraphEdit.model_validate({
        "action": "connect",
        "from": "u1",
        "to": "u2",
        "from_port": "0",
        "to_port": "0",
    })

    try:
        apply_graph_edit(current, edit)
    except ValueError as e:
        assert "uplicate" in str(e)
    else:
        raise AssertionError("expected ValueError for duplicate connection")


def test_graph_edit_connect_allows_same_units_different_ports():
    """Same endpoints with different ports are distinct edges."""
    current = ProcessGraph.model_validate({
        "units": [
            {"id": "u1", "type": "Source", "controllable": False, "params": {}},
            {"id": "u2", "type": "Valve", "controllable": True, "params": {}},
        ],
        "connections": [
            {"from": "u1", "to": "u2", "from_port": "0", "to_port": "0"}
        ],
    })
    edit = GraphEdit.model_validate({
        "action": "connect",
        "from": "u1",
        "to": "u2",
        "from_port": "0",
        "to_port": "1",
    })

    out = apply_graph_edit(current, edit)
    conns = out.connections
    assert len(conns) == 2


def test_graph_edit_replace_graph_rejects_duplicate_connections():
    """replace_graph must not contain duplicate edges."""
    current = ProcessGraph.model_validate({"units": [], "connections": []})
    edit = GraphEdit.model_validate({
        "action": "replace_graph",
        "units": [
            {"id": "a", "type": "Source", "controllable": False, "params": {}},
            {"id": "b", "type": "Valve", "controllable": True, "params": {}},
        ],
        "connections": [
            {"from": "a", "to": "b", "from_port": "0", "to_port": "0"},
            {"from": "a", "to": "b", "from_port": "0", "to_port": "0"},
        ],
    })

    try:
        apply_graph_edit(current, edit)
    except ValueError as e:
        assert "uplicate" in str(e)
    else:
        raise AssertionError(
            "expected ValueError for duplicate connection in replace_graph"
        )


def test_graph_edit_replace_graph_allows_same_units_different_ports():
    """Same unit pair with different ports is valid in replace_graph."""
    current = ProcessGraph.model_validate({"units": [], "connections": []})
    edit = GraphEdit.model_validate({
        "action": "replace_graph",
        "units": [
            {"id": "a", "type": "Source", "controllable": False, "params": {}},
            {"id": "b", "type": "Valve", "controllable": True, "params": {}},
        ],
        "connections": [
            {"from": "a", "to": "b", "from_port": "0", "to_port": "0"},
            {"from": "a", "to": "b", "from_port": "0", "to_port": "1"},
        ],
    })

    out = apply_graph_edit(current, edit)
    assert len(out.connections) == 2



async def test_process_agent_connect_with_ports():
    """Connect with explicit ports and verify they're stored."""
    base = REPO_ROOT / "config" / "examples" / "temperature_process.yaml"
    graph = load_process_graph_from_file(base)
    edit = GraphEdit.model_validate({
        "action": "connect",
        "from": "hot_source",
        "to": "cold_valve",
        "from_port": "1",
        "to_port": "0",
    })

    result = await _apply_graph_edits_workflow(graph, edit)
    conn = next(
        (
            c for c in result.connections
            if c.from_id == "hot_source" and c.to_id == "cold_valve"
        ),
        None,
    )
    assert conn is not None, "Expected connection hot_source -> cold_valve"
    assert conn.from_port == "1"
    assert conn.to_port == "0"


async def test_apply_training_config_edits_workflow_merge():
    base = REPO_ROOT / "config" / "examples" / "training_config.yaml"
    config = load_training_config_from_file(base)
    edit = {"rewards": {"weights": {"dumping": -0.2}}}
    result = await _apply_training_edits_workflow(config, edit)
    assert result.rewards.weights["dumping"] == -0.2
    assert result.goal.target_temp == config.goal.target_temp


async def _run_all_tests():
    await test_process_agent_add_unit()
    await test_process_agent_connect()

    test_graph_edit_connect_rejects_duplicate_same_ports()
    test_graph_edit_connect_allows_same_units_different_ports()
    test_graph_edit_replace_graph_rejects_duplicate_connections()
    test_graph_edit_replace_graph_allows_same_units_different_ports()

    await test_process_agent_connect_with_ports()
    await test_apply_training_config_edits_workflow_merge()


if __name__ == "__main__":
    import asyncio

    asyncio.run(_run_all_tests())
    print("All agent tests passed.")
