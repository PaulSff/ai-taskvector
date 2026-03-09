"""
Canonical schemas for process graph and training config.
All consumers (env factory, training script, assistants) use these only.
"""
from core.schemas.process_graph import (
    CodeBlock,
    EnvironmentType,
    NodePosition,
    Unit,
    Connection,
    ProcessGraph,
)
from core.schemas.agent_node import (
    RL_AGENT_NODE_TYPES,
    get_agent_node,
    get_agent_model_dir,
    has_agent_node,
)

# Re-export Connection (used by normalizer and consumers)
from core.schemas.training_config import (
    EnvironmentConfig,
    FormulaComponent,
    GoalConfig,
    RewardRule,
    RewardsConfig,
    HyperparametersConfig,
    CallbacksConfig,
    TrainingConfig,
)
from core.schemas.external_io_spec import ObservationSpecItem, ActionSpecItem, ExternalIOSpec

__all__ = [
    "CodeBlock",
    "EnvironmentType",
    "NodePosition",
    "Unit",
    "Connection",
    "ProcessGraph",
    "RL_AGENT_NODE_TYPES",
    "get_agent_node",
    "get_agent_model_dir",
    "has_agent_node",
    "EnvironmentConfig",
    "FormulaComponent",
    "GoalConfig",
    "RewardRule",
    "RewardsConfig",
    "HyperparametersConfig",
    "CallbacksConfig",
    "TrainingConfig",
    "ObservationSpecItem",
    "ActionSpecItem",
    "ExternalIOSpec",
]
