"""
RL Agent node convention for roundtrip (Node-RED, EdgeLinkd, PyFlow).

An "RL Agent" node in a workflow is a unit with type in RL_AGENT_NODE_TYPES.
Its id (or params.agent_id) is the agent name and maps to the model folder: models/<agent_name>/.
See docs/DEPLOYMENT_NODERED.md § Import scenarios.
"""
from pathlib import Path

from schemas.process_graph import ProcessGraph, Unit

# Unit types we treat as the RL Agent / Process Controller node in the workflow
RL_AGENT_NODE_TYPES = ("RLAgent", "ProcessController", "rl_agent", "process_controller")


def get_agent_node(graph: ProcessGraph) -> Unit | None:
    """
    Return the first unit in the graph that is an RL Agent node (type in RL_AGENT_NODE_TYPES).
    Returns None if none found.
    """
    for u in graph.units:
        if u.type in RL_AGENT_NODE_TYPES:
            return u
    return None


def get_agent_model_dir(unit: Unit, base_dir: str | Path = "models") -> Path:
    """
    Resolve the model directory for an agent node: base_dir / agent_name.
    agent_name = unit.params.get("agent_id") or unit.id.
    """
    base = Path(base_dir)
    name = (unit.params.get("agent_id") or unit.params.get("model_name") or unit.id).strip()
    if not name:
        name = "rl_agent"
    return base / name


def has_agent_node(graph: ProcessGraph) -> bool:
    """True if the graph contains at least one unit with type in RL_AGENT_NODE_TYPES."""
    return get_agent_node(graph) is not None
