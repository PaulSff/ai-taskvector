"""
ComfyUI custom nodes for AI Control RL: RLOracleStepDriver, RLOracleCollector, RLAgentPredict.

Install: copy this folder into ComfyUI/custom_nodes/ai_control_rl/
"""
from .rloracle import RLOracleStepDriverNode, RLOracleCollectorNode
from .rl_agent import RLAgentPredictNode

NODE_CLASS_MAPPINGS = {
    "RLOracleStepDriver": RLOracleStepDriverNode,
    "RLOracleCollector": RLOracleCollectorNode,
    "RLAgentPredict": RLAgentPredictNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RLOracleStepDriver": "RLOracle Step Driver",
    "RLOracleCollector": "RLOracle Collector",
    "RLAgentPredict": "RL Agent Predict",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
