"""
RL Agent node convention for roundtrip (Node-RED, EdgeLinkd, PyFlow).

An "RL Agent" node in a workflow is a unit with type in RL_AGENT_NODE_TYPES.
Its id (or params.agent_id) is the agent name and maps to the model folder: models/<agent_name>/.
See docs/DEPLOYMENT_NODERED.md § Import scenarios.
"""
from pathlib import Path

from schemas.process_graph import ProcessGraph, Unit
from units.registry import get_unit_spec

# Canonical unit types for agent nodes. Aliases (e.g. rl_agent, llm_agent) are
# normalized to these by the normalizer on input; the rest of the system uses only these.
RL_AGENT_NODE_TYPES = ("RLAgent",)
LLM_AGENT_NODE_TYPES = ("LLMAgent",)

# Node types excluded from graph executor (policy/service nodes run via adapters)
EXECUTOR_EXCLUDED_TYPES = RL_AGENT_NODE_TYPES + ("RLOracle",) + LLM_AGENT_NODE_TYPES


def get_policy_node(graph: ProcessGraph) -> Unit | None:
    """
    Return the policy node used for observation/action wiring: first RLAgent, else first LLMAgent.
    Used by the executor and env_factory for obs sources and action targets.
    """
    for u in graph.units:
        if u.type in RL_AGENT_NODE_TYPES:
            return u
    for u in graph.units:
        if u.type in LLM_AGENT_NODE_TYPES:
            return u
    return None


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


def get_agent_observation_input_ids(graph: ProcessGraph) -> list[str]:
    """
    Return ordered unit ids that feed into the policy node (observations).
    Policy node = first RLAgent, else first LLMAgent. Order: sorted by source unit id.
    """
    agent = get_policy_node(graph)
    if agent is None:
        return []
    into = [c.from_id for c in graph.connections if c.to_id == agent.id]
    return sorted(into)


def get_agent_action_output_ids(graph: ProcessGraph) -> list[str]:
    """
    Return ordered unit ids that the policy node feeds into (actions).
    Policy node = first RLAgent, else first LLMAgent. Order: sorted by target unit id.
    """
    agent = get_policy_node(graph)
    if agent is None:
        return []
    out = [c.to_id for c in graph.connections if c.from_id == agent.id]
    return sorted(out)


def get_llm_agent_node(graph: ProcessGraph) -> Unit | None:
    """Return the first unit with type in LLM_AGENT_NODE_TYPES, or None."""
    for u in graph.units:
        if u.type in LLM_AGENT_NODE_TYPES:
            return u
    return None


def has_llm_agent_node(graph: ProcessGraph) -> bool:
    """True if the graph contains at least one LLMAgent unit."""
    return get_llm_agent_node(graph) is not None


# --- Canonical training flow (role-based: step_driver, join, switch) ---


def get_unit_by_role(graph: ProcessGraph, role: str) -> Unit | None:
    """First unit whose registered spec has the given role, or None. Type-agnostic."""
    for u in graph.units:
        spec = get_unit_spec(u.type)
        if spec is not None and spec.role == role:
            return u
    return None


def get_step_driver(graph: ProcessGraph) -> Unit | None:
    """First unit with role step_driver (canonical reset/step trigger), or None."""
    return get_unit_by_role(graph, "step_driver")


def get_join(graph: ProcessGraph) -> Unit | None:
    """First unit with role join (collector). Observation vector is read from its output."""
    return get_unit_by_role(graph, "join")


def get_switch(graph: ProcessGraph) -> Unit | None:
    """First unit with role switch. Action vector is injected into its input."""
    return get_unit_by_role(graph, "switch")


def get_switch_action_target_ids(graph: ProcessGraph) -> list[str]:
    """Ordered unit ids that receive from the Switch (action targets). Sorted by target id."""
    sw = get_switch(graph)
    if sw is None:
        return []
    return sorted(c.to_id for c in graph.connections if c.from_id == sw.id)


def has_canonical_topology(graph: ProcessGraph) -> bool:
    """True if graph has units with roles step_driver, join, and switch (canonical training flow)."""
    return (
        get_step_driver(graph) is not None
        and get_join(graph) is not None
        and get_switch(graph) is not None
    )
