#!/usr/bin/env python3
"""
Minimal test: load example configs via normalizer and assert canonical schema.
Run from repo root: python scripts/test_normalizer.py
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from normalizer import (
    load_process_graph_from_file,
    load_training_config_from_file,
    to_process_graph,
)
from schemas import ProcessGraph, TrainingConfig


def test_node_red_adapter():
    """Node-RED flow JSON → canonical ProcessGraph (Phase 5.1)."""
    config_dir = REPO_ROOT / "config" / "examples"
    node_red_path = config_dir / "temperature_process_node_red.json"
    text = node_red_path.read_text()
    graph = to_process_graph(text, format="node_red")
    assert graph.environment_type.value == "thermodynamic"
    assert len(graph.units) == 7
    assert len(graph.connections) == 6
    assert graph.get_unit("mixer_tank") is not None
    assert graph.get_unit("mixer_tank").type == "Tank"
    # mixer_tank → dump_valve and mixer_tank → thermometer
    from_ids = [c.from_id for c in graph.connections]
    to_ids = [c.to_id for c in graph.connections]
    assert ("mixer_tank", "dump_valve") in list(zip(from_ids, to_ids))
    assert ("mixer_tank", "thermometer") in list(zip(from_ids, to_ids))
    # Load from file with inferred format (.json → node_red)
    graph2 = load_process_graph_from_file(node_red_path)
    assert len(graph2.units) == 7 and len(graph2.connections) == 6


def test_node_red_full_workflow():
    """Node-RED full support: all nodes included, code_blocks from function/exec nodes."""
    raw = [
        {"id": "src", "type": "Source", "wires": [["fn"]], "params": {"temp": 50}},
        {"id": "fn", "type": "function", "wires": [["out"]], "func": "return { payload: msg.payload * 2 };"},
        {"id": "out", "type": "debug", "wires": []},
    ]
    graph = to_process_graph(raw, format="node_red")
    assert len(graph.units) == 3
    assert len(graph.connections) == 2  # src→fn, fn→out
    assert graph.get_unit("fn").type == "function"
    assert len(graph.code_blocks) == 1
    assert graph.code_blocks[0].id == "fn"
    assert graph.code_blocks[0].language == "javascript"
    assert "msg.payload * 2" in graph.code_blocks[0].source


def test_template_adapter():
    """Template (blocks/links or units/connections) → canonical ProcessGraph (Phase 5.2)."""
    config_dir = REPO_ROOT / "config" / "examples"
    template_path = config_dir / "temperature_process_template.json"
    text = template_path.read_text()
    graph = to_process_graph(text, format="template")
    assert graph.environment_type.value == "thermodynamic"
    assert len(graph.units) == 7
    assert len(graph.connections) == 6
    assert graph.get_unit("mixer_tank").type == "Tank"
    assert graph.get_unit("hot_valve").controllable is True


def test_pyflow_adapter():
    """PyFlow graph (nodes/connections or graphs[].nodes) → canonical ProcessGraph + code_blocks."""
    # Minimal PyFlow-like structure: nodes list + connections
    raw = {
        "environment_type": "thermodynamic",
        "nodes": [
            {"id": "n1", "name": "Source", "type": "Source", "params": {"temp": 80}},
            {"id": "n2", "type": "Valve", "controllable": True},
            {"id": "n3", "type": "Tank"},
            {"id": "n4", "type": "Sensor", "code": "# sense temp\nreturn state['T']", "language": "python"},
        ],
        "connections": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}, {"from": "n3", "to": "n4"}],
    }
    graph = to_process_graph(raw, format="pyflow")
    assert graph.environment_type.value == "thermodynamic"
    assert len(graph.units) == 4
    assert len(graph.connections) == 3
    assert graph.get_unit("n1").type == "Source"
    assert graph.get_unit("n4").type == "Sensor"
    assert len(graph.code_blocks) == 1
    assert graph.code_blocks[0].id == "n4"
    assert graph.code_blocks[0].language == "python"
    assert "state['T']" in graph.code_blocks[0].source


def test_ryven_adapter():
    """Ryven project (scripts[].flow or flow/nodes + connections) → canonical ProcessGraph + code_blocks."""
    # Minimal Ryven-like: scripts[0].flow with nodes and links
    raw = {
        "environment_type": "thermodynamic",
        "scripts": [
            {
                "flow": {
                    "nodes": [
                        {"id": "r1", "title": "Source", "type": "Source", "data": {"temp": 80}},
                        {"id": "r2", "type": "Valve", "controllable": True, "data": {}},
                        {"id": "r3", "type": "Sensor", "data": {"source": "return inputs.get('r2', 0.0)"}},
                    ],
                    "connections": [{"from": "r1", "to": "r2"}, {"from": "r2", "to": "r3"}],
                },
            },
        ],
    }
    graph = to_process_graph(raw, format="ryven")
    assert graph.environment_type.value == "thermodynamic"
    assert len(graph.units) == 3
    assert len(graph.connections) == 2
    assert graph.get_unit("r1").type == "Source"
    assert graph.get_unit("r3").type == "Sensor"
    assert len(graph.code_blocks) == 1
    assert graph.code_blocks[0].id == "r3"
    assert "inputs.get" in graph.code_blocks[0].source
    # Top-level flow/nodes variant
    raw2 = {"flow": {"nodes": [{"id": "a", "type": "Node"}], "links": []}}
    graph2 = to_process_graph(raw2, format="ryven")
    assert len(graph2.units) == 1 and graph2.get_unit("a").type == "Node"


def test_n8n_adapter():
    """n8n workflow JSON (nodes + connections keyed by node name) → canonical ProcessGraph + code_blocks."""
    raw = {
        "name": "Demo",
        "nodes": [
            {"id": "a1", "name": "Chat Trigger", "type": "n8n-nodes-base.trigger", "typeVersion": 1, "position": [100, 100], "parameters": {}},
            {"id": "a2", "name": "Processor", "type": "n8n-nodes-base.code", "typeVersion": 1, "position": [300, 100], "parameters": {"jsCode": "return [{ json: { x: 1 } }];"}},
            {"id": "a3", "name": "Output", "type": "n8n-nodes-base.noOp", "typeVersion": 1, "position": [500, 100], "parameters": {}},
        ],
        "connections": {
            "Chat Trigger": {"main": [[{"node": "Processor", "type": "main", "index": 0}]]},
            "Processor": {"main": [[{"node": "Output", "type": "main", "index": 0}]]},
        },
    }
    graph = to_process_graph(raw, format="n8n")
    assert graph.environment_type.value == "thermodynamic"
    assert len(graph.units) == 3
    assert len(graph.connections) == 2
    assert graph.get_unit("Chat Trigger").type == "trigger"
    assert graph.get_unit("Processor").type == "code"
    assert len(graph.code_blocks) == 1
    assert graph.code_blocks[0].id == "Processor"
    assert graph.code_blocks[0].language == "javascript"
    assert "json: { x: 1 }" in graph.code_blocks[0].source


def main():
    config_dir = REPO_ROOT / "config" / "examples"
    process_path = config_dir / "temperature_process.yaml"
    training_path = config_dir / "training_config.yaml"

    print("Loading process graph via normalizer...")
    process: ProcessGraph = load_process_graph_from_file(process_path)
    print(f"  environment_type: {process.environment_type}")
    print(f"  units: {len(process.units)}")
    print(f"  connections: {len(process.connections)}")
    assert process.environment_type.value == "thermodynamic"
    assert len(process.units) == 11  # sources, tank, valves, thermometers, water_level, rl_agent
    assert len(process.connections) == 16
    print("  OK")

    print("Loading training config via normalizer...")
    training: TrainingConfig = load_training_config_from_file(training_path)
    print(f"  goal.target_temp: {training.goal.target_temp}")
    print(f"  algorithm: {training.algorithm}")
    print(f"  hyperparameters.learning_rate: {training.hyperparameters.learning_rate}")
    assert training.goal.target_temp == 37.0
    assert training.algorithm == "PPO"
    assert training.hyperparameters.learning_rate == 3e-4
    print("  OK")

    print("Testing Node-RED adapter...")
    test_node_red_adapter()
    print("  OK")
    print("Testing Node-RED full workflow (all nodes + code_blocks)...")
    test_node_red_full_workflow()
    print("  OK")
    print("Testing template adapter...")
    test_template_adapter()
    print("  OK")
    print("Testing PyFlow adapter...")
    test_pyflow_adapter()
    print("  OK")
    print("Testing Ryven adapter...")
    test_ryven_adapter()
    print("  OK")
    print("Testing n8n adapter...")
    test_n8n_adapter()
    print("  OK")

    print("\nAll normalizer tests passed. Canonical schemas and normalizer are consistent.")


if __name__ == "__main__":
    main()
