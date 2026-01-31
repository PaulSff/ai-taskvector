"""
Canonical schemas for process graph and training config.
All consumers (env factory, training script, assistants) use these only.
"""
from schemas.process_graph import (
    EnvironmentType,
    Unit,
    Connection,
    ProcessGraph,
)

# Re-export Connection (used by normalizer and consumers)
from schemas.training_config import (
    GoalConfig,
    RewardsConfig,
    HyperparametersConfig,
    CallbacksConfig,
    TrainingConfig,
)

__all__ = [
    "EnvironmentType",
    "Unit",
    "Connection",
    "ProcessGraph",
    "GoalConfig",
    "RewardsConfig",
    "HyperparametersConfig",
    "CallbacksConfig",
    "TrainingConfig",
]
