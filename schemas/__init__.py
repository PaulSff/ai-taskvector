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
from schemas.agent_node import (
    RL_AGENT_NODE_TYPES,
    get_agent_node,
    get_agent_model_dir,
    has_agent_node,
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
    "RL_AGENT_NODE_TYPES",
    "get_agent_node",
    "get_agent_model_dir",
    "has_agent_node",
    "EnvironmentConfig",
    "GoalConfig",
    "RewardRule",
    "RewardsConfig",
    "HyperparametersConfig",
    "CallbacksConfig",
    "TrainingConfig",
]
