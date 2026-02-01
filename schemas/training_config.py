"""
Canonical training config schema.
Single source of truth for goal, rewards, algorithm, hyperparameters.
"""
from pydantic import BaseModel, Field


class GoalConfig(BaseModel):
    """Goal / setpoint configuration for the control task."""

    type: str = Field(default="setpoint", description="Goal type: setpoint, range, multi_objective")
    target_temp: float | None = Field(default=None, description="Target temperature (°C)")
    target_volume_ratio: tuple[float, float] | None = Field(
        default=None,
        description="Target volume ratio range (e.g. (0.80, 0.85))",
    )
    target_pressure_range: tuple[float, float] | None = Field(default=None, description="Target pressure range [min, max]")


class RewardsConfig(BaseModel):
    """Reward configuration: preset and/or custom weights."""

    preset: str = Field(
        default="temperature_and_volume",
        description="Preset name: temperature_and_volume, pressure_control, goal_reaching, exploration",
    )
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "temp_error": -1.0,
            "volume_in_range": 10.0,
            "dumping": -0.1,
            "step_penalty": -0.001,
        },
        description="Component weights (negative=penalty, positive=bonus)",
    )


class HyperparametersConfig(BaseModel):
    """Algorithm hyperparameters (PPO, SAC, etc.)."""

    learning_rate: float = Field(default=3e-4, description="Learning rate")
    n_steps: int = Field(default=2048, description="Steps per update (PPO)")
    batch_size: int = Field(default=64, description="Batch size")
    n_epochs: int = Field(default=10, description="Epochs per update (PPO)")
    gamma: float = Field(default=0.99, description="Discount factor")
    gae_lambda: float = Field(default=0.95, description="GAE lambda")
    clip_range: float = Field(default=0.2, description="PPO clip range")
    ent_coef: float = Field(default=0.01, description="Entropy coefficient")


class RunConfig(BaseModel):
    """Run settings: vec env size, randomization, verbosity, post-train test."""

    n_envs: int = Field(default=4, description="Number of parallel envs for vectorized training")
    randomize_params: bool = Field(default=True, description="Randomize env params (e.g. target temp) during training")
    verbose: int = Field(default=1, description="SB3 verbosity (0=none, 1=info)")
    test_episodes: int = Field(default=5, description="Number of test episodes to run after training")


class CallbacksConfig(BaseModel):
    """Training callbacks: eval and checkpoint frequency and paths."""

    eval_freq: int = Field(default=5000, description="Evaluate and maybe save best model every N steps")
    save_freq: int = Field(default=10000, description="Save checkpoint every N steps")
    model_dir: str | None = Field(
        default=None,
        description="If set, all callback paths are under this directory (e.g. models/temperature-control-agent).",
    )
    save_path: str = Field(default="./models/checkpoints/", description="Checkpoint directory")
    name_prefix: str = Field(default="ppo_temp_control", description="Checkpoint filename prefix")
    best_model_save_path: str = Field(default="./models/best/", description="Best model save directory")
    log_path: str = Field(default="./logs/eval/", description="Eval logs directory")
    tensorboard_log: str = Field(default="./logs/tensorboard/", description="TensorBoard log directory")
    final_model_save_path: str = Field(
        default="./models/ppo_temperature_control_final",
        description="Path to save the final model after training",
    )


class TrainingConfig(BaseModel):
    """Canonical training config: goal, rewards, algorithm, hyperparameters, run, callbacks."""

    goal: GoalConfig = Field(default_factory=GoalConfig, description="Goal/setpoint config")
    rewards: RewardsConfig = Field(default_factory=RewardsConfig, description="Reward config")
    algorithm: str = Field(default="PPO", description="Algorithm: PPO, SAC, etc.")
    hyperparameters: HyperparametersConfig = Field(
        default_factory=HyperparametersConfig,
        description="Algorithm hyperparameters",
    )
    total_timesteps: int = Field(default=100000, description="Total env steps to train (overridable by CLI --timesteps)")
    run: RunConfig = Field(default_factory=RunConfig, description="Run settings (n_envs, randomize_params, verbose, test_episodes)")
    callbacks: CallbacksConfig = Field(
        default_factory=CallbacksConfig,
        description="Eval and checkpoint callback settings",
    )
