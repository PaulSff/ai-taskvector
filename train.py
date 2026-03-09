"""
Training script for the temperature control AI agent.
Uses Stable-Baselines3 with PPO algorithm.

Config-driven: train.py --config <training_config.yaml> [--process-config <process.yaml>]
Loads canonical config via normalizer. Environment (runtime) is chosen by config.environment:
  - source: native → env_factory from process graph (GraphEnv wraps GraphExecutor; training uses executor step/reset API)
  - source: external → Node-RED / EdgeLinkd / PyFlow adapter (config.environment.adapter + adapter_config)
  - source: gymnasium → gym.make(env_id, **env_kwargs)
Each model's training_config_used.yaml stores the environment block for reproducibility.
"""
import os
import argparse
from pathlib import Path

import yaml
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.monitor import Monitor

from environments import get_env, EnvSource


def _load_normalizer_and_factory():
    from normalizer import load_training_config_from_file, load_process_graph_from_file
    from env_factory import build_env
    return load_training_config_from_file, load_process_graph_from_file, build_env


def _resolve_process_graph(training_config, process_config_path: Path | None):
    """Resolve process graph from CLI, config.environment.process_graph_path, or default. Used when source=native."""
    load_process_graph_from_file = _load_normalizer_and_factory()[1]
    if process_config_path is not None and process_config_path.exists():
        return load_process_graph_from_file(process_config_path)
    path_from_config = training_config.environment.process_graph_path
    if path_from_config and Path(path_from_config).exists():
        return load_process_graph_from_file(Path(path_from_config))
    default_process = Path(__file__).resolve().parent / "config" / "examples" / "temperature_process.yaml"
    if default_process.exists():
        return load_process_graph_from_file(default_process)
    raise FileNotFoundError(
        "No process config found. Use --process-config <path> or set environment.process_graph_path in config."
    )


def run_training_from_config(
    config_path: str | Path,
    process_config_path: str | Path | None = None,
    checkpoint_path: str | None = None,
    total_timesteps: int | None = None,
):
    """Run training from canonical config. Environment (runtime) from config.environment; CLI --timesteps overrides total_timesteps."""
    load_training_config_from_file, load_process_graph_from_file, build_env = _load_normalizer_and_factory()

    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Training config not found: {config_path}")

    print("Loading training config via normalizer...")
    training_config = load_training_config_from_file(config_path)
    env_cfg = training_config.environment
    goal = training_config.goal
    hyper = training_config.hyperparameters
    run_cfg = training_config.run
    cb = training_config.callbacks
    steps = total_timesteps if total_timesteps is not None else training_config.total_timesteps

    process_graph = None
    if env_cfg.source == "native":
        process_config_path = Path(process_config_path) if process_config_path else None
        print("Loading process config via normalizer...")
        process_graph = _resolve_process_graph(training_config, process_config_path)

    n_envs = run_cfg.n_envs
    if env_cfg.source == "external":
        n_envs = min(n_envs, 1)  # External runtimes are typically single-instance
        if n_envs < run_cfg.n_envs:
            print(f"Using n_envs=1 for external adapter (config had n_envs={run_cfg.n_envs})")

    def make_env():
        if env_cfg.source == "native":
            return build_env(
                process_graph, goal,
                rewards=training_config.rewards,
                randomize_params=run_cfg.randomize_params,
            )
        if env_cfg.source == "external":
            return get_env(EnvSource.EXTERNAL, {
                "adapter": env_cfg.adapter,
                "config": env_cfg.adapter_config,
                "adapter_config": env_cfg.adapter_config,
            })
        if env_cfg.source == "gymnasium":
            return get_env(EnvSource.GYMNASIUM, {
                "env_id": env_cfg.env_id,
                **env_cfg.env_kwargs,
            })
        raise ValueError(f"Unknown environment source: {env_cfg.source}")

    print(f"Creating environment (source={env_cfg.source})...")
    vec_env = make_vec_env(make_env, n_envs=n_envs)
    eval_env = Monitor(make_env())

    # Ensure output dirs exist (from config paths)
    os.makedirs(cb.save_path, exist_ok=True)
    os.makedirs(cb.best_model_save_path, exist_ok=True)
    os.makedirs(cb.log_path, exist_ok=True)
    try:
        import tensorboard  # noqa: F401
        tb_log = cb.tensorboard_log
    except ImportError:
        tb_log = None
    if tb_log:
        os.makedirs(tb_log, exist_ok=True)

    # Persist used config alongside checkpoints for reproducibility
    config_save_dir = Path(cb.save_path.rstrip("/")).resolve().parent
    training_config_used_path = config_save_dir / "training_config_used.yaml"
    with open(training_config_used_path, "w") as f:
        yaml.dump(training_config.model_dump(), f, default_flow_style=False, sort_keys=False)
    if process_graph is not None:
        process_config_used_path = config_save_dir / "process_config_used.yaml"
        with open(process_config_used_path, "w") as f:
            yaml.dump(process_graph.model_dump(by_alias=True), f, default_flow_style=False, sort_keys=False)
        print(f"Config saved to {training_config_used_path} and {process_config_used_path}")
    else:
        print(f"Config saved to {training_config_used_path}")

    if checkpoint_path and os.path.exists(checkpoint_path):
        print(f"Loading model from checkpoint: {checkpoint_path}")
        model = PPO.load(checkpoint_path, env=vec_env)
        current_timesteps = model.num_timesteps
        print(f"Resuming from {current_timesteps:,} timesteps (additional {steps:,})")
    else:
        if checkpoint_path:
            print(f"Warning: Checkpoint {checkpoint_path} not found. Starting from scratch.")
        print("Initializing PPO from config hyperparameters...")
        model = PPO(
            "MlpPolicy",
            vec_env,
            learning_rate=hyper.learning_rate,
            n_steps=hyper.n_steps,
            batch_size=hyper.batch_size,
            n_epochs=hyper.n_epochs,
            gamma=hyper.gamma,
            gae_lambda=hyper.gae_lambda,
            clip_range=hyper.clip_range,
            ent_coef=hyper.ent_coef,
            verbose=run_cfg.verbose,
            tensorboard_log=tb_log,
        )
        current_timesteps = 0

    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=cb.best_model_save_path,
        log_path=cb.log_path,
        eval_freq=cb.eval_freq,
        deterministic=True,
        render=False,
    )
    checkpoint_callback = CheckpointCallback(
        save_freq=cb.save_freq,
        save_path=cb.save_path,
        name_prefix=cb.name_prefix,
    )

    target_timesteps = current_timesteps + steps
    print(f"Training for {steps:,} timesteps (total target: {target_timesteps:,})")
    if tb_log:
        print(f"Check TensorBoard logs at: {tb_log}")

    try:
        import tqdm  # noqa: F401
        import rich  # noqa: F401
        progress_bar = True
    except ImportError:
        progress_bar = False

    model.learn(
        total_timesteps=target_timesteps,
        callback=[eval_callback, checkpoint_callback],
        progress_bar=progress_bar,
        reset_num_timesteps=False,
    )

    model.save(cb.final_model_save_path)
    print(f"\nTraining complete! Model saved to {cb.final_model_save_path}")

    print("\nTesting trained model...")
    test_episode(eval_env, model, num_episodes=run_cfg.test_episodes)

    vec_env.close()
    eval_env.close()


def test_episode(env, model, num_episodes=1):
    """Test the trained model on a few episodes. Works for any gym.Env; thermodynamic-specific stats only when available."""
    for episode in range(num_episodes):
        obs, info = env.reset()
        done = False
        total_reward = 0
        steps = 0

        print(f"\n=== Episode {episode + 1} ===")

        while not done:
            action, _states = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            total_reward += reward
            steps += 1

            if steps % 10 == 0:
                try:
                    env.render()
                except NotImplementedError:
                    pass

        print(f"Episode finished after {steps} steps, total reward: {total_reward:.2f}")
        target_temp = getattr(env, "target_temp", None)
        if target_temp is not None and "temperature" in info:
            volume_ratio = info.get("volume_ratio")
            if volume_ratio is None and getattr(env, "tank_capacity", 0) > 0:
                volume_ratio = getattr(env, "volume", 0) / env.tank_capacity
            temp_success = abs(info["temperature"] - target_temp) < 0.1
            volume_success = volume_ratio is not None and 0.80 <= volume_ratio <= 0.85
            print(f"  Temperature: {info['temperature']:.2f}°C (target {target_temp}°C) {'✓' if temp_success else '✗'}")
            if volume_ratio is not None:
                print(f"  Volume ratio: {volume_ratio*100:.1f}% {'✓' if volume_success else '✗'}")
            print(f"  Success: {'✓' if (temp_success and volume_success) else '✗'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train temperature control AI agent with PPO (config-driven)")
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to canonical training config YAML (normalizer + env factory + SB3).",
    )
    parser.add_argument(
        "--process-config",
        type=str,
        default=None,
        help="Path to canonical process graph YAML (optional; default: config/examples/temperature_process.yaml).",
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=None,
        help="Path to checkpoint to resume (e.g., ./models/temperature-control-agent/checkpoints/ppo_temp_control_80000_steps.zip)",
    )
    parser.add_argument(
        "--timesteps",
        type=int,
        default=100000,
        help="Number of timesteps to train (default: 100000). If resuming, this is additional timesteps.",
    )
    args = parser.parse_args()

    run_training_from_config(
        config_path=args.config,
        process_config_path=args.process_config,
        checkpoint_path=args.checkpoint,
        total_timesteps=args.timesteps,
    )

