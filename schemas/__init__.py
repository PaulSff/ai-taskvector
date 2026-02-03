"""
Canonical schemas for process graph and training config.
All consumers (env factory, training script, assistants) use these only.
"""
from schemas.process_graph import (
    CodeBlock,
    EnvironmentType,
    Unit,
    Connection,
    ProcessGraph,
)

# Re-export Connection (used by normalizer and consumers)
from schemas.training_config import (
    EnvironmentConfig,
    GoalConfig,
    RewardRule,
    RewardsConfig,
    HyperparametersConfig,
    CallbacksConfig,
    TrainingConfig,
)

__all__ = [
    "CodeBlock",
    "EnvironmentType",
    "Unit",
    "Connection",
    "ProcessGraph",
    "EnvironmentConfig",
    "GoalConfig",
    "RewardRule",
    "RewardsConfig",
    "HyperparametersConfig",
    "CallbacksConfig",
    "TrainingConfig",
]
