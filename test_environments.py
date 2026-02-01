"""
Test environments/get_env: Gymnasium, Custom (thermodynamic).
Run with venv: python test_environments.py
"""
from pathlib import Path

from environments import get_env, EnvSource


def test_custom_thermodynamic():
    config = {
        "process_graph_path": str(Path(__file__).parent / "config" / "examples" / "temperature_process.yaml"),
        "goal": {"target_temp": 37.0, "target_volume_ratio": [0.80, 0.85]},
    }
    env = get_env(EnvSource.CUSTOM, config)
    obs, info = env.reset()
    assert obs is not None
    assert env.observation_space.contains(obs)
    env.close()


def test_gymnasium():
    env = get_env(EnvSource.GYMNASIUM, {"env_id": "CartPole-v1", "kwargs": {}})
    obs, info = env.reset()
    assert obs is not None
    env.close()


if __name__ == "__main__":
    test_custom_thermodynamic()
    print("Custom thermodynamic OK")
    test_gymnasium()
    print("Gymnasium OK")
    print("All environment tests passed.")
