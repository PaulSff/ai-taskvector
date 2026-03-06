#!/usr/bin/env python3
"""
Test runtime execution using the custom temperature control workflow.

Loads the wired workflow (thermodynamic + canonical + RLAgent) from
config/examples/custom_runtime_factory/custom_AI_temperature-control-agent/,
builds GraphEnv via env_factory, and runs reset + multiple steps.
Uses random actions so no trained model is required; optional: use policy if best_model exists.
Run from repo root: python scripts/test_custom_runtime_workflow.py
"""
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from normalizer import load_process_graph_from_file, load_training_config_from_file
from env_factory import build_env


def main():
    base = REPO_ROOT / "config" / "examples" / "custom_runtime_factory" / "custom_AI_temperature-control-agent"
    process_path = base / "temperature_workflow_wired.yaml"
    training_path = base / "training_config_custom.yaml"

    if not process_path.exists():
        raise FileNotFoundError(f"Workflow not found: {process_path}")

    print("Loading workflow and training config...")
    process_graph = load_process_graph_from_file(process_path)
    if training_path.exists():
        training_config = load_training_config_from_file(training_path)
        goal = training_config.goal
    else:
        from schemas.training_config import GoalConfig
        goal = GoalConfig(type="setpoint", target_temp=37.0, target_volume_ratio=(0.80, 0.85))

    print(f"  environment_type: {process_graph.environment_type}")
    print(f"  units: {len(process_graph.units)} (including Random, RLAgent)")
    print(f"  goal.target_temp: {getattr(goal, 'target_temp', None)}")

    print("Building env (canonical topology injected if needed)...")
    env = build_env(process_graph, goal, randomize_params=False)
    print(f"  env: {type(env).__name__}")
    print(f"  obs_space: {env.observation_space.shape}, action_space: {env.action_space.shape}")

    print("Running reset() and 10 steps (random actions)...")
    obs, info = env.reset()
    assert obs is not None and len(obs) == env.observation_space.shape[0], "obs shape mismatch"
    for step in range(10):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        assert obs is not None
        assert isinstance(reward, (int, float, np.floating))
        if terminated or truncated:
            break
    env.close()
    print(f"  completed {step + 1} steps, final reward: {reward:.4f}")

    print("\nCustom runtime workflow test passed.")


if __name__ == "__main__":
    main()
