"""
Deploy trained model as a node in a workflow (Node-RED / EdgeLinkd flow JSON).

Injects an RL Agent node into the flow and wires it to observation sources and action targets.
See docs/DEPLOYMENT_NODERED.md.
"""
from deploy.flow_inject import inject_agent_into_flow

__all__ = ["inject_agent_into_flow"]
