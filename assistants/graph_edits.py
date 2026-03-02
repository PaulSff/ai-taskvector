"""
Graph edit schema and apply logic for Process Assistant.
Edits are applied to a graph dict; then normalizer.to_process_graph(updated) yields canonical ProcessGraph.
"""
from typing import Any, Literal

from pydantic import BaseModel, Field

from schemas.agent_node import LLM_AGENT_NODE_TYPES, RL_AGENT_NODE_TYPES

from deploy.agent_inject import (
    render_llm_agent_predict_js,
    render_llm_agent_predict_n8n,
    render_llm_agent_predict_py,
    render_rl_agent_predict_js,
    render_rl_agent_predict_n8n,
    render_rl_agent_predict_py,
)
from deploy.oracle_inject import inject_oracle_into_graph_dict


# Action types matching ENVIRONMENT_PROCESS_ASSISTANT.md §6
GraphEditAction = Literal[
    "add_unit", "remove_unit", "connect", "disconnect", "no_edit", "replace_graph", "replace_unit", "add_code_block",
    "import_unit", "import_workflow",
]

# Runtime/origin → code language (Node-RED/EdgeLinkd/n8n → javascript; PyFlow/Ryven/ComfyUI → python)
_ORIGIN_LANGUAGE: dict[str, str] = {
    "canonical": "python",
    "node_red": "javascript",
    "edgelinkd": "javascript",
    "n8n": "javascript",
    "pyflow": "python",
    "ryven": "python",
    "comfyui": "python",
}


class FindUnit(BaseModel):
    """Unit selector for replace_unit (unit to find and remove)."""

    id: str = Field(..., description="Unit id to find and replace")


class GraphEditCodeBlock(BaseModel):
    """Code block payload for add_code_block (id = unit_id; one block per unit)."""

    id: str = Field(..., description="Unit id this code block belongs to")
    language: str = Field(..., description="Language: javascript (Node-RED/n8n), python (PyFlow/Ryven)")
    source: str = Field(default="", description="Raw source code")


class GraphEditUnit(BaseModel):
    """Unit payload for add_unit edit."""

    id: str = Field(..., description="Unique unit identifier")
    type: str = Field(..., description="Unit type: Source, Valve, Tank, Sensor, etc.")
    controllable: bool = Field(default=False, description="Whether this unit is an action/control input")
    params: dict[str, Any] = Field(default_factory=dict, description="Type-specific parameters")


class GraphEdit(BaseModel):
    """Structured graph edit from Process Assistant (validate in backend)."""

    action: GraphEditAction = Field(
        ...,
        description="add_unit | remove_unit | connect | disconnect | no_edit | replace_graph | replace_unit | add_code_block",
    )
    unit_id: str | None = Field(default=None, description="For remove_unit")
    unit: GraphEditUnit | None = Field(default=None, description="For add_unit")
    code_block: GraphEditCodeBlock | None = Field(default=None, description="For add_code_block")
    find_unit: FindUnit | None = Field(default=None, description="For replace_unit: unit to find")
    replace_with: GraphEditUnit | None = Field(default=None, description="For replace_unit: new unit")
    from_id: str | None = Field(default=None, alias="from", description="Source unit id for connect/disconnect")
    to_id: str | None = Field(default=None, alias="to", description="Target unit id for connect/disconnect")
    from_port: str | None = Field(default=None, description="Source output port index for connect (default '0')")
    to_port: str | None = Field(default=None, description="Target input port index for connect (default '0')")
    reason: str | None = Field(default=None, description="For no_edit")
    units: list[dict[str, Any]] | None = Field(default=None, description="For replace_graph: full unit list")
    connections: list[dict[str, str]] | None = Field(default=None, description="For replace_graph: full connection list")
    # import_unit: node_id from RAG catalogue; unit_id optional (for import_unit: target unit id)
    node_id: str | None = Field(default=None, description="For import_unit: catalogue node id from RAG")
    # import_workflow: source = file path or URL
    source: str | None = Field(default=None, description="For import_workflow: file path or URL")
    merge: bool = Field(default=False, description="For import_workflow: merge into current graph instead of replace")

    model_config = {"populate_by_name": True}


def _normalize_edit(edit: dict[str, Any]) -> dict[str, Any]:
    """If edit has units+connections but no action, treat as replace_graph."""
    if edit.get("action") is not None:
        return dict(edit)
    if isinstance(edit.get("units"), list) and isinstance(edit.get("connections"), list):
        return {**edit, "action": "replace_graph"}
    return dict(edit)


def _language_for_origin(origin: dict[str, Any] | None) -> str | None:
    """Return expected code language from origin (runtime), or None if unknown."""
    if not origin or not isinstance(origin, dict):
        return None
    for key in _ORIGIN_LANGUAGE:
        if origin.get(key) is not None:
            return _ORIGIN_LANGUAGE[key]
    return None


def _validate_connect_disconnect(parsed: GraphEdit) -> None:
    """Raise if connect/disconnect is missing required from/to parameters."""
    if parsed.action == "connect":
        if parsed.from_id is None or parsed.to_id is None:
            missing = [k for k, v in [("from", parsed.from_id), ("to", parsed.to_id)] if v is None]
            raise ValueError(
                f"Incorrect format for connect: missing required parameter(s): {', '.join(missing)}"
            )
    elif parsed.action == "disconnect":
        if parsed.from_id is None or parsed.to_id is None:
            missing = [k for k, v in [("from", parsed.from_id), ("to", parsed.to_id)] if v is None]
            raise ValueError(
                f"Incorrect format for disconnect: missing required parameter(s): {', '.join(missing)}"
            )


def apply_graph_edit(current: dict[str, Any], edit: dict[str, Any]) -> dict[str, Any]:
    """
    Apply a single graph edit to the current graph (dict).
    Returns updated dict suitable for normalizer.to_process_graph(updated, format="dict").
    Does not validate the result; normalizer will.
    Raises ValueError for invalid edits (missing params, non-existent unit/connection).
    """
    edit = _normalize_edit(edit)
    parsed = GraphEdit.model_validate(edit)
    if parsed.action == "no_edit":
        return dict(current)
    if parsed.action in ("import_unit", "import_workflow"):
        raise ValueError(
            "import_unit and import_workflow must be resolved via apply_workflow_edits with rag_index_dir"
        )

    add_code_block_payload: dict[str, Any] | None = None
    add_oracle_code_blocks: list[dict[str, Any]] = []
    env_type = current.get("environment_type", "thermodynamic")
    units: list[dict[str, Any]] = [u.copy() for u in current.get("units", [])]
    connections: list[dict[str, Any]] = []
    for c in current.get("connections", []):
        from_id = c.get("from") or c.get("from_id")
        to_id = c.get("to") or c.get("to_id")
        if from_id is not None and to_id is not None:
            conn: dict[str, Any] = {"from": str(from_id), "to": str(to_id)}
            conn["from_port"] = str(c.get("from_port", "0"))
            conn["to_port"] = str(c.get("to_port", "0"))
            connections.append(conn)

    if parsed.action == "add_unit" and parsed.unit is not None:
        u = parsed.unit
        if any(x["id"] == u.id for x in units):
            raise ValueError(f"Unit id already exists: {u.id}")
        if u.type == "RLOracle":
            adapter_config = dict(u.params.get("adapter_config") or u.params)
            origin = current.get("origin") or {}
            lang = _language_for_origin(origin) or "python"
            obs_ids = (
                u.params.get("observation_source_ids")
                or adapter_config.get("observation_sources")
                or adapter_config.get("observation_source_ids")
            )
            cbs = inject_oracle_into_graph_dict(
                units, adapter_config, u.id,
                language=lang,
                observation_source_ids=obs_ids if isinstance(obs_ids, list) else None,
                n8n_mode=origin.get("n8n") is not None,
            )
            add_oracle_code_blocks.extend(cbs)
        elif u.type in RL_AGENT_NODE_TYPES:
            model_path = u.params.get("model_path", "")
            unit_ids = {x.get("id") for x in units if isinstance(x, dict)}
            # Derive obs/act from graph connections when not in params
            obs_ids = u.params.get("observation_source_ids") or sorted(
                c.get("from") or c.get("from_id")
                for c in connections
                if (c.get("to") or c.get("to_id")) == u.id
                if c.get("from") or c.get("from_id")
            )
            act_ids = u.params.get("action_target_ids") or sorted(
                c.get("to") or c.get("to_id")
                for c in connections
                if (c.get("from") or c.get("from_id")) == u.id
                if c.get("to") or c.get("to_id")
            )
            inference_url = str(u.params.get("inference_url") or "http://127.0.0.1:8000/predict")
            for sid in obs_ids:
                if sid in unit_ids:
                    connections.append({"from": sid, "to": u.id, "from_port": "0", "to_port": "0"})
            for tid in act_ids:
                if tid in unit_ids:
                    connections.append({"from": u.id, "to": tid, "from_port": "0", "to_port": "0"})
            units.append({
                "id": u.id,
                "type": u.type,
                "controllable": False,
                "params": {"model_path": model_path, **{k: v for k, v in u.params.items() if k not in ("observation_source_ids", "action_target_ids")}},
            })
            # Add template-based code_block: Python for PyFlow/Ryven; JS for Node-RED; n8n template for n8n
            origin = current.get("origin") or {}
            lang = _language_for_origin(origin) or "python"
            if lang == "python":
                code_src = render_rl_agent_predict_py(inference_url, obs_ids if obs_ids else [])
                add_oracle_code_blocks.append({"id": u.id, "language": "python", "source": code_src})
            elif origin.get("n8n") is not None:
                code_src = render_rl_agent_predict_n8n(inference_url, obs_ids if obs_ids else [])
                add_oracle_code_blocks.append({"id": u.id, "language": "javascript", "source": code_src})
            else:
                code_src = render_rl_agent_predict_js(inference_url, obs_ids if obs_ids else [])
                add_oracle_code_blocks.append({"id": u.id, "language": "javascript", "source": code_src})
        elif u.type in LLM_AGENT_NODE_TYPES:
            unit_ids = {x.get("id") for x in units if isinstance(x, dict)}
            obs_ids = u.params.get("observation_source_ids") or sorted(
                c.get("from") or c.get("from_id")
                for c in connections
                if (c.get("to") or c.get("to_id")) == u.id
                if c.get("from") or c.get("from_id")
            )
            act_ids = u.params.get("action_target_ids") or sorted(
                c.get("to") or c.get("to_id")
                for c in connections
                if (c.get("from") or c.get("from_id")) == u.id
                if c.get("to") or c.get("to_id")
            )
            inference_url = str(u.params.get("inference_url") or "http://127.0.0.1:8001/predict")
            system_prompt = str(u.params.get("system_prompt") or "You are a control agent. Given observations, output a JSON object with an 'action' key containing a list of numbers.")
            user_prompt_template = str(u.params.get("user_prompt_template") or "Observations: {observation_json}. Output only a JSON object with key 'action' and value a list of numbers.")
            model_name = str(u.params.get("model_name") or "llama3.2")
            provider = str(u.params.get("provider") or "ollama")
            host = str(u.params.get("host") or "")
            for sid in obs_ids:
                if sid in unit_ids:
                    connections.append({"from": sid, "to": u.id, "from_port": "0", "to_port": "0"})
            for tid in act_ids:
                if tid in unit_ids:
                    connections.append({"from": u.id, "to": tid, "from_port": "0", "to_port": "0"})
            llm_params = {k: v for k, v in u.params.items() if k not in ("observation_source_ids", "action_target_ids")}
            units.append({
                "id": u.id,
                "type": u.type,
                "controllable": False,
                "params": llm_params,
            })
            origin = current.get("origin") or {}
            lang = _language_for_origin(origin) or "python"
            if lang == "python":
                code_src = render_llm_agent_predict_py(
                    inference_url, obs_ids if obs_ids else [],
                    system_prompt, user_prompt_template, model_name, provider, host,
                )
                add_oracle_code_blocks.append({"id": u.id, "language": "python", "source": code_src})
            elif origin.get("n8n") is not None:
                code_src = render_llm_agent_predict_n8n(
                    inference_url, obs_ids if obs_ids else [],
                    system_prompt, user_prompt_template, model_name, provider, host,
                )
                add_oracle_code_blocks.append({"id": u.id, "language": "javascript", "source": code_src})
            else:
                code_src = render_llm_agent_predict_js(
                    inference_url, obs_ids if obs_ids else [],
                    system_prompt, user_prompt_template, model_name, provider, host,
                )
                add_oracle_code_blocks.append({"id": u.id, "language": "javascript", "source": code_src})
        else:
            units.append({
                "id": u.id,
                "type": u.type,
                "controllable": u.controllable,
                "params": dict(u.params),
            })

    elif parsed.action == "remove_unit":
        if parsed.unit_id is None:
            raise ValueError("Incorrect format for remove_unit: missing required parameter: unit_id")
        uid = parsed.unit_id
        to_remove: set[str] = {uid}
        if uid.endswith("_step_driver"):
            other = uid[:-12] + "_collector"
            if any(x.get("id") == other for x in units):
                to_remove.add(other)
        elif uid.endswith("_collector"):
            other = uid[:-9] + "_step_driver"
            if any(x.get("id") == other for x in units):
                to_remove.add(other)
        if not any(x.get("id") == uid for x in units):
            raise ValueError(f"Unit id does not exist: {uid}")
        units = [x for x in units if x.get("id") not in to_remove]
        connections = [
            c for c in connections
            if c.get("from") not in to_remove and c.get("to") not in to_remove
        ]

    elif parsed.action == "connect":
        _validate_connect_disconnect(parsed)
        from_id, to_id = parsed.from_id, parsed.to_id
        unit_ids = {u.get("id") for u in units}
        # RLOracle expands to step_driver + collector: observations -> collector, step_driver -> process
        if to_id + "_collector" in unit_ids and to_id not in unit_ids:
            to_id = to_id + "_collector"
        if from_id + "_step_driver" in unit_ids and from_id not in unit_ids:
            from_id = from_id + "_step_driver"
        if from_id not in unit_ids:
            raise ValueError(f"Unit id does not exist: {parsed.from_id}")
        if to_id not in unit_ids:
            raise ValueError(f"Unit id does not exist: {parsed.to_id}")
        from_port = str(parsed.from_port) if parsed.from_port is not None else "0"
        to_port = str(parsed.to_port) if parsed.to_port is not None else "0"
        connections.append({"from": from_id, "to": to_id, "from_port": from_port, "to_port": to_port})

    elif parsed.action == "disconnect":
        _validate_connect_disconnect(parsed)
        from_id, to_id = parsed.from_id, parsed.to_id
        unit_ids = {u.get("id") for u in units}
        if to_id + "_collector" in unit_ids and to_id not in unit_ids:
            to_id = to_id + "_collector"
        if from_id + "_step_driver" in unit_ids and from_id not in unit_ids:
            from_id = from_id + "_step_driver"
        # Match by from/to (optionally from_port/to_port if specified)
        from_port = str(parsed.from_port) if parsed.from_port is not None else None
        to_port = str(parsed.to_port) if parsed.to_port is not None else None
        matching = [
            c for c in connections
            if c.get("from") == from_id and c.get("to") == to_id
            and (from_port is None or c.get("from_port", "0") == from_port)
            and (to_port is None or c.get("to_port", "0") == to_port)
        ]
        if not matching:
            raise ValueError(
                f"Connection does not exist: from={parsed.from_id}, to={parsed.to_id}"
                + (f" (from_port={from_port}, to_port={to_port})" if from_port or to_port else "")
            )
        connections = [
            c for c in connections
            if not (c.get("from") == from_id and c.get("to") == to_id
                    and (from_port is None or c.get("from_port", "0") == from_port)
                    and (to_port is None or c.get("to_port", "0") == to_port))
        ]

    elif parsed.action == "replace_unit":
        if parsed.find_unit is None or parsed.replace_with is None:
            raise ValueError(
                "Incorrect format for replace_unit: missing required parameter(s): find_unit, replace_with"
            )
        old_id = parsed.find_unit.id
        new_unit = parsed.replace_with
        new_id = new_unit.id
        if not any(x.get("id") == old_id for x in units):
            raise ValueError(f"Unit id does not exist: {old_id}")
        if old_id != new_id and any(x.get("id") == new_id for x in units):
            raise ValueError(f"Unit id already exists: {new_id}")
        # Remove old unit
        units = [x for x in units if x.get("id") != old_id]
        # Add new unit
        units.append({
            "id": new_id,
            "type": new_unit.type,
            "controllable": new_unit.controllable,
            "params": dict(new_unit.params),
        })
        # Reconnect: replace old_id with new_id in all connections
        for c in connections:
            if c.get("from") == old_id:
                c["from"] = new_id
            if c.get("to") == old_id:
                c["to"] = new_id

    elif parsed.action == "add_code_block":
        if parsed.code_block is None:
            raise ValueError(
                "Incorrect format for add_code_block: missing required parameter: code_block"
            )
        cb = parsed.code_block
        unit_ids = {u.get("id") for u in units}
        if cb.id not in unit_ids:
            raise ValueError(f"Unit id does not exist: {cb.id}")
        expected_lang = _language_for_origin(current.get("origin"))
        if expected_lang is not None and cb.language.lower() != expected_lang:
            raise ValueError(
                f"Language must match origin runtime: expected '{expected_lang}' (e.g. Node-RED→javascript, PyFlow→python), got '{cb.language}'"
            )
        # add_code_block mutates code_blocks below; we mark it here
        add_code_block_payload = {"id": cb.id, "language": cb.language, "source": cb.source}

    elif parsed.action == "replace_graph" and parsed.units is not None and parsed.connections is not None:
        # Full graph replacement: normalize unit/connection dicts to have id, type, controllable, params / from, to
        units = []
        for u in parsed.units:
            if isinstance(u, dict):
                units.append({
                    "id": str(u.get("id", "")),
                    "type": str(u.get("type", "Unit")),
                    "controllable": bool(u.get("controllable", False)),
                    "params": dict(u.get("params", {})),
                })
        connections = []
        for c in parsed.connections:
            if isinstance(c, dict):
                from_id = c.get("from") or c.get("from_id")
                to_id = c.get("to") or c.get("to_id")
                if from_id is not None and to_id is not None:
                    connections.append({
                        "from": str(from_id),
                        "to": str(to_id),
                        "from_port": str(c.get("from_port", "0")),
                        "to_port": str(c.get("to_port", "0")),
                    })

    # Preserve code_blocks and layout for units that still exist
    final_unit_ids = {u.get("id") for u in units if u.get("id")}
    code_blocks = [
        cb for cb in current.get("code_blocks", [])
        if isinstance(cb, dict) and cb.get("id") in final_unit_ids
    ]
    if add_code_block_payload is not None:
        code_blocks = [cb for cb in code_blocks if cb.get("id") != add_code_block_payload["id"]]
        code_blocks.append(add_code_block_payload)
    code_blocks.extend(add_oracle_code_blocks)
    layout = dict(current.get("layout") or {})
    if parsed.action == "replace_unit" and parsed.find_unit and parsed.replace_with:
        old_id, new_id = parsed.find_unit.id, parsed.replace_with.id
        if old_id in layout and new_id not in layout:
            layout[new_id] = layout[old_id]
    layout = {k: v for k, v in layout.items() if k in final_unit_ids}

    result: dict[str, Any] = {
        "environment_type": env_type,
        "units": units,
        "connections": connections,
    }
    if code_blocks:
        result["code_blocks"] = code_blocks
    if layout:
        result["layout"] = layout
    if current.get("origin_format") is not None:
        result["origin_format"] = current["origin_format"]
    if current.get("origin") is not None:
        result["origin"] = current["origin"]
    return result
