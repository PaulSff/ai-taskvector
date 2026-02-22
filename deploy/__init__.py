"""
Deploy trained model as a node in a workflow (Node-RED / EdgeLinkd / PyFlow).

Injects an RL Agent node into the flow and wires it to observation sources and action targets.
See docs/DEPLOYMENT_NODERED.md and docs/WORKFLOW_EDITORS_AND_CODE.md.
"""
from deploy.flow_inject import inject_agent_into_flow, inject_agent_into_pyflow_flow

__all__ = ["inject_agent_into_flow", "inject_agent_into_pyflow_flow"]
