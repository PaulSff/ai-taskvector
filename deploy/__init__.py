"""
Deploy trained model as a node in a workflow (Node-RED / EdgeLinkd / PyFlow).

Injects an RL Agent node into the flow and wires it to observation sources and action targets.
Also injects RLOracle (step handler) for external-runtime training — universal, env-agnostic,
all params from adapter_config, no embedded simulations.
Template-based RLAgent: prepare + http request + parse nodes that call an inference service
(POST /predict). Run: python -m server.inference_server --model path/to/model.zip
See docs/DEPLOYMENT_NODERED.md and docs/WORKFLOW_EDITORS_AND_CODE.md.
"""
from deploy.agent_inject import inject_agent_template_into_flow
from deploy.flow_inject import (
    inject_agent_into_comfyui_workflow,
    inject_agent_into_flow,
    inject_agent_into_n8n_flow,
    inject_agent_into_pyflow_flow,
    inject_llm_agent_into_flow,
    inject_llm_agent_into_n8n_flow,
    inject_llm_agent_into_pyflow_flow,
)
__all__ = [
    "inject_agent_into_comfyui_workflow",
    "inject_agent_into_flow",
    "inject_agent_into_n8n_flow",
    "inject_agent_into_pyflow_flow",
    "inject_agent_template_into_flow",
    "inject_llm_agent_into_flow",
    "inject_llm_agent_into_n8n_flow",
    "inject_llm_agent_into_pyflow_flow",
]
