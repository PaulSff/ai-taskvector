"""
Shared canonicalization for the normalizer pipeline.
Import modules produce dicts; to_process_graph uses these helpers to build ProcessGraph.
"""
from typing import Any

# Unit types and controllable flag come from the unit spec (units/registry.py). Canonical agent/oracle
# type names and their aliases are below (resolved in _canonical_unit_type).
CANONICAL_RL_AGENT_TYPE = "RLAgent"
CANONICAL_LLM_AGENT_TYPE = "LLMAgent"
CANONICAL_RL_ORACLE_TYPE = "RLOracle"
CANONICAL_RL_GYM_TYPE = "RLGym"

_RL_AGENT_TYPE_ALIASES = {"rl_agent"}
_LLM_AGENT_TYPE_ALIASES = {"llm_agent"}
_RL_ORACLE_TYPE_ALIASES = {"rl_oracle"}
_RL_GYM_TYPE_ALIASES = {"rl_gym"}

def infer_environments_from_unit_types(unit_types: list[str]) -> list[str]:
    """
    Infer environment tags from unit types using the unit registry (type-agnostic).
    Each registered UnitSpec may set environment_tags (e.g. ["thermodynamic"], ["data_bi"], ["canonical"], ["RL training"]).
    Returns a sorted list of unique tags present in the graph. Call after all relevant unit modules are registered.
    """
    from units.registry import get_unit_spec

    seen: set[str] = set()
    for t in unit_types:
        if not t:
            continue
        spec = get_unit_spec(t)
        if spec and spec.environment_tags:
            for tag in spec.environment_tags:
                seen.add(tag)
    return sorted(seen)


def _canonical_unit_type(typ: str) -> str:
    """Return canonical unit type. Resolves agent/oracle/gym aliases to RLAgent, LLMAgent, RLOracle, RLGym."""
    if not typ:
        return typ
    key = typ.strip()
    low = key.lower().replace("-", "_")
    if low in _RL_AGENT_TYPE_ALIASES or key == CANONICAL_RL_AGENT_TYPE:
        return CANONICAL_RL_AGENT_TYPE
    if low in _LLM_AGENT_TYPE_ALIASES or key == CANONICAL_LLM_AGENT_TYPE:
        return CANONICAL_LLM_AGENT_TYPE
    if low in _RL_ORACLE_TYPE_ALIASES or key == CANONICAL_RL_ORACLE_TYPE:
        return CANONICAL_RL_ORACLE_TYPE
    if low in _RL_GYM_TYPE_ALIASES or key == CANONICAL_RL_GYM_TYPE:
        return CANONICAL_RL_GYM_TYPE
    return key


def _ensure_list_connections(raw: list[Any]) -> list[dict[str, Any]]:
    """Ensure each connection has 'from', 'to', 'from_port', 'to_port'. Port indices default to '0' when missing. Preserves connection_type when present."""
    out: list[dict[str, Any]] = []
    for c in raw:
        if isinstance(c, dict):
            from_id = c.get("from") or c.get("from_id")
            to_id = c.get("to") or c.get("to_id")
            if from_id is not None and to_id is not None:
                from_port = c.get("from_port")
                to_port = c.get("to_port")
                entry: dict[str, Any] = {
                    "from": str(from_id),
                    "to": str(to_id),
                    "from_port": str(from_port) if from_port is not None else "0",
                    "to_port": str(to_port) if to_port is not None else "0",
                }
                if c.get("connection_type") is not None:
                    entry["connection_type"] = str(c["connection_type"])
                out.append(entry)
    return out
