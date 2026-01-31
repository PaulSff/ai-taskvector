#!/usr/bin/env python3
"""
Minimal test: load example configs via normalizer and assert canonical schema.
Run: python test_normalizer.py
"""
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from normalizer import (
    load_process_graph_from_file,
    load_training_config_from_file,
    to_process_graph,
)
from schemas import ProcessGraph, TrainingConfig


def test_node_red_adapter():
    """Node-RED flow JSON → canonical ProcessGraph (Phase 5.1)."""
    config_dir = Path(__file__).parent / "config" / "examples"
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


def test_template_adapter():
    """Template (blocks/links or units/connections) → canonical ProcessGraph (Phase 5.2)."""
    config_dir = Path(__file__).parent / "config" / "examples"
    template_path = config_dir / "temperature_process_template.json"
    text = template_path.read_text()
    graph = to_process_graph(text, format="template")
    assert graph.environment_type.value == "thermodynamic"
    assert len(graph.units) == 7
    assert len(graph.connections) == 6
    assert graph.get_unit("mixer_tank").type == "Tank"
    assert graph.get_unit("hot_valve").controllable is True


def main():
    config_dir = Path(__file__).parent / "config" / "examples"
    process_path = config_dir / "temperature_process.yaml"
    training_path = config_dir / "training_config.yaml"

    print("Loading process graph via normalizer...")
    process: ProcessGraph = load_process_graph_from_file(process_path)
    print(f"  environment_type: {process.environment_type}")
    print(f"  units: {len(process.units)}")
    print(f"  connections: {len(process.connections)}")
    assert process.environment_type.value == "thermodynamic"
    assert len(process.units) == 7
    assert len(process.connections) == 6
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
    print("Testing template adapter...")
    test_template_adapter()
    print("  OK")

    print("\nAll normalizer tests passed. Canonical schemas and normalizer are consistent.")


if __name__ == "__main__":
    main()
