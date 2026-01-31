#!/usr/bin/env python3
"""
Minimal test: load example configs via normalizer and assert canonical schema.
Run: python test_normalizer.py
"""
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from normalizer import load_process_graph_from_file, load_training_config_from_file
from schemas import ProcessGraph, TrainingConfig


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

    print("\nAll normalizer tests passed. Canonical schemas and normalizer are consistent.")


if __name__ == "__main__":
    main()
