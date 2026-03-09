#!/usr/bin/env python3
"""
Test env factory: load canonical configs via normalizer, build env via factory, run reset/step.
Run from repo root: python scripts/test_env_factory.py
"""
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from normalizer import load_process_graph_from_file, load_training_config_from_file
from env_factory import build_env


def main():
    config_dir = REPO_ROOT / "config" / "examples"
    # Use wired workflow (RLAgent with observation/action wiring) so factory can inject canonical topology
    process_path = config_dir / "native_runtime_factory" / "native_AI_temperature-control-agent" / "temperature_workflow_wired.yaml"
    if not process_path.exists():
        process_path = config_dir / "temperature_process.yaml"
    training_path = config_dir / "training_config.yaml"

    print("Loading process graph and training config via normalizer...")
    process_graph = load_process_graph_from_file(process_path)
    training_config = load_training_config_from_file(training_path)
    goal = training_config.goal
    print(f"  environment_type: {process_graph.environment_type}")
    print(f"  goal.target_temp: {goal.target_temp}")

    print("Building env via factory...")
    env = build_env(process_graph, goal, randomize_params=False)
    print(f"  env: {type(env).__name__}")

    print("Running reset() and one step()...")
    obs, info = env.reset()
    assert obs is not None and len(obs) == env.observation_space.shape[0]
    action = env.action_space.sample()
    obs, reward, terminated, truncated, info = env.step(action)
    assert obs is not None
    assert isinstance(reward, (int, float, np.floating))
    env.close()
    print("  OK")

    print("\nEnv factory test passed. Canonical graph + goal -> Gymnasium env works.")


if __name__ == "__main__":
    main()
