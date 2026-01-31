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


class TrainingConfig(BaseModel):
    """Canonical training config: goal, rewards, algorithm, hyperparameters."""

    goal: GoalConfig = Field(default_factory=GoalConfig, description="Goal/setpoint config")
    rewards: RewardsConfig = Field(default_factory=RewardsConfig, description="Reward config")
    algorithm: str = Field(default="PPO", description="Algorithm: PPO, SAC, etc.")
    hyperparameters: HyperparametersConfig = Field(
        default_factory=HyperparametersConfig,
        description="Algorithm hyperparameters",
    )
