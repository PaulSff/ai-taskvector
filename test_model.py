"""
Test a trained model (config-driven, universal).
Uses config, normalizer, and environment type like train.py.
No environment-specific visualization; use environments/custom/water_tank_simulator.py for water-tank viz.
"""
import argparse
from pathlib import Path

from stable_baselines3 import PPO

from environments import get_env, EnvSource


def _env_config_from_training(config_path: Path, process_config_path: Path | None) -> dict:
    """Build env config dict from training config and optional process config path."""
    from normalizer import load_training_config_from_file
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Training config not found: {config_path}")
    training_config = load_training_config_from_file(config_path)
    if process_config_path is None:
        process_config_path = Path(__file__).resolve().parent / "config" / "examples" / "temperature_process.yaml"
    process_config_path = Path(process_config_path)
    if not process_config_path.exists():
        raise FileNotFoundError(f"Process config not found: {process_config_path}")
    return {
        "process_graph_path": str(process_config_path.resolve()),
        "goal": training_config.goal.model_dump(),
    }


def run_test(
    config_path: Path | str,
    model_path: Path | str,
    process_config_path: Path | str | None = None,
    num_episodes: int = 5,
    env_source: str = "CUSTOM",
    deterministic: bool = True,
):
    """
    Run test episodes with a trained model. Env and goal from config (same as training).
    """
    config_path = Path(config_path)
    model_path = Path(model_path)
    if not model_path.exists():
        model_path_zip = Path(str(model_path) + ".zip")
        if model_path_zip.exists():
            model_path = model_path_zip
        else:
            raise FileNotFoundError(
                f"Model not found: {model_path} (or {model_path}.zip). "
                "Train first (Run training in the GUI or run train.py) or set model path to an existing model."
            )

    source = EnvSource[env_source] if isinstance(env_source, str) else env_source
    if source != EnvSource.CUSTOM:
        raise NotImplementedError(
            "Config-driven test currently supports CUSTOM only. "
            "Use get_env() directly or extend run_test for other sources."
        )
    env_config = _env_config_from_training(config_path, process_config_path)
    env = get_env(source, env_config)

    print(f"Loading model from {model_path}...")
    model = PPO.load(str(model_path))

    successes = 0
    total_steps = 0
    total_reward_sum = 0.0

    for episode in range(num_episodes):
        obs, info = env.reset()
        done = False
        steps = 0
        reward_sum = 0.0

        while not done:
            action, _ = model.predict(obs, deterministic=deterministic)
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            steps += 1
            reward_sum += reward

        total_steps += steps
        total_reward_sum += reward_sum

        # Success: temperature and volume in range (thermodynamic env)
        volume_ratio = info.get("volume_ratio", getattr(env, "volume", 0) / max(getattr(env, "tank_capacity", 1), 1e-6))
        target_temp = getattr(env, "target_temp", None)
        temp_ok = (target_temp is None or
                   abs(info.get("temperature", 0) - target_temp) < 0.1)
        volume_ok = (0.80 <= volume_ratio <= 0.85)
        success = temp_ok and volume_ok
        if success:
            successes += 1

        print(f"Episode {episode + 1}: steps={steps}, reward_sum={reward_sum:.1f}, "
              f"temp={info.get('temperature', 'N/A')}, vol_ratio={volume_ratio*100:.1f}%, "
              f"success={'✓' if success else '✗'}")

    env.close()

    print(f"\n--- Summary ---")
    print(f"Episodes: {num_episodes}, Successes: {successes}, Success rate: {successes/num_episodes*100:.1f}%")
    print(f"Total steps: {total_steps}, Mean reward/episode: {total_reward_sum/num_episodes:.1f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test a trained model (config-driven, no visualization). Use water_tank_simulator for tank viz."
    )
    parser.add_argument(
        "model_path",
        nargs="?",
        default="./models/temperature-control-agent/best/best_model",
        help="Path to trained model.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/examples/training_config.yaml",
        help="Training config (for goal + env).",
    )
    parser.add_argument(
        "--process-config",
        type=str,
        default=None,
        help="Process graph YAML (default: config/examples/temperature_process.yaml).",
    )
    parser.add_argument(
        "--episodes",
        type=int,
        default=5,
        help="Number of test episodes.",
    )
    parser.add_argument(
        "--env-source",
        type=str,
        default="CUSTOM",
        choices=["CUSTOM", "GYMNASIUM", "EXTERNAL"],
        help="Environment source (default: CUSTOM).",
    )
    parser.add_argument(
        "--stochastic",
        action="store_true",
        help="Use stochastic policy instead of deterministic.",
    )
    args = parser.parse_args()

    run_test(
        config_path=args.config,
        model_path=args.model_path,
        process_config_path=args.process_config,
        num_episodes=args.episodes,
        env_source=args.env_source,
        deterministic=not args.stochastic,
    )
