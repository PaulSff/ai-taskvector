"""NodeRedWorkflowExtract unit: self-contained Node-RED workflow extractor aligned with extractors.py node-red behavior."""
from units.rag.node_red_workflow_extractor.node_red_workflow_extractor import (
    NODE_RED_WORKFLOW_EXTRACT_INPUT_PORTS,
    NODE_RED_WORKFLOW_EXTRACT_OUTPUT_PORTS,
    register_node_red_workflow_extract,
)

__all__ = [
    "register_node_red_workflow_extract",
    "NODE_RED_WORKFLOW_EXTRACT_INPUT_PORTS",
    "NODE_RED_WORKFLOW_EXTRACT_OUTPUT_PORTS",
]
