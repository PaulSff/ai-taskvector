"""
Canonical schemas for process graph and training config.
All consumers (env factory, training script, agents) use these only.
"""

from core.schemas.agent_node import (
    RL_AGENT_NODE_TYPES,
    get_agent_model_dir,
    get_agent_node,
    has_agent_node,
)
from core.schemas.external_io_spec import (
    ActionSpecItem,
    ExternalIOSpec,
    ObservationSpecItem,
)
from core.schemas.process_graph import (
    CodeBlock,
    Connection,
    EnvironmentType,
    NodePosition,
    ProcessGraph,
    Unit,
)

# Re-export Connection (used by normalizer and consumers)
from core.schemas.training_config import (
    CallbacksConfig,
    EnvironmentConfig,
    FormulaComponent,
    GoalConfig,
    HyperparametersConfig,
    RewardRule,
    RewardsConfig,
    TrainingConfig,
)

__all__ = [
    "RL_AGENT_NODE_TYPES",
    "ActionSpecItem",
    "CallbacksConfig",
    "CodeBlock",
    "Connection",
    "EnvironmentConfig",
    "EnvironmentType",
    "ExternalIOSpec",
    "FormulaComponent",
    "GoalConfig",
    "HyperparametersConfig",
    "NodePosition",
    "ObservationSpecItem",
    "ProcessGraph",
    "RewardRule",
    "RewardsConfig",
    "TrainingConfig",
    "Unit",
    "get_agent_model_dir",
    "get_agent_node",
    "has_agent_node",
]
