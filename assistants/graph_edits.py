"""
Graph edit schema and apply logic for Process Assistant.
Edits are applied to a graph dict; then normalizer.to_process_graph(updated) yields canonical ProcessGraph.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4
import json

from pydantic import BaseModel, Field

from schemas.agent_node import LLM_AGENT_NODE_TYPES, RL_AGENT_NODE_TYPES, RL_GYM_NODE_TYPE

from deploy.agent_inject import (
    render_llm_agent_predict_js,
    render_llm_agent_predict_n8n,
    render_llm_agent_predict_py,
    render_rl_agent_predict_js,
    render_rl_agent_predict_n8n,
    render_rl_agent_predict_py,
)
from deploy.oracle_inject import render_oracle_code_blocks_for_canonical
from units.node_red import get_node_red_template, get_node_red_types
from units.n8n import get_n8n_template, get_n8n_types
from units.pyflow import get_pyflow_template, get_pyflow_types
from units.registry import get_unit_spec, get_type_by_role

from assistants.prompts import (
    WORKFLOW_DESIGNER_ADD_PIPELINE_REQUIRED_TYPES_ERROR,
    WORKFLOW_DESIGNER_ADD_PIPELINE_USE_ADD_UNIT_ERROR,
)
from normalizer.runtime_detector import runtime_label
from normalizer.system_comments import (
    PIPELINE_WIRING_BASE,
    PIPELINE_WIRING_PREFIX_LLMAGENT,
    PIPELINE_WIRING_PREFIX_RLAGENT,
    PIPELINE_WIRING_PREFIX_RLGYM,
    PIPELINE_WIRING_PREFIX_RLORACLE,
)
from assistants.todo_list import add_task as todo_add_task
from assistants.todo_list import ensure_todo_list as todo_ensure_list
from assistants.todo_list import mark_completed as todo_mark_completed
from assistants.todo_list import remove_task as todo_remove_task

# App setting: coding_is_allowed (read from config/app_settings.json so graph_edits has no gui dependency)
_CODING_IS_ALLOWED_KEY = "coding_is_allowed"
_CODING_IS_ALLOWED_DEFAULT = False


def _coding_is_allowed() -> bool:
    """Return True if app setting coding_is_allowed is True (default). Read from config/app_settings.json."""
    try:
        config_path = Path(__file__).resolve().parent.parent / "config" / "app_settings.json"
        if not config_path.is_file():
            return _CODING_IS_ALLOWED_DEFAULT
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _CODING_IS_ALLOWED_DEFAULT
        return bool(data.get(_CODING_IS_ALLOWED_KEY, _CODING_IS_ALLOWED_DEFAULT))
    except (OSError, json.JSONDecodeError):
        return _CODING_IS_ALLOWED_DEFAULT


# Action types matching ENVIRONMENT_PROCESS_ASSISTANT.md §6
GraphEditAction = Literal[
    "add_unit", "add_pipeline", "remove_unit", "connect", "disconnect", "no_edit", "replace_graph", "replace_unit",
    "add_code_block", "add_comment",
    "add_todo_list", "remove_todo_list", "add_task", "remove_task", "mark_completed",
    "add_environment",
    "import_unit", "import_workflow",
]

# Pipeline types: RLGym, RLOracle, RLSet, LLMSet. Not graph "units" — they describe a training/serving pipeline.
# Use add_pipeline with "pipeline" payload. Unit types (Source, Valve, RLAgent, LLMAgent, etc.) use add_unit.
PIPELINE_TYPES: frozenset[str] = frozenset([RL_GYM_NODE_TYPE, "RLOracle", "RLSet", "LLMSet"])


def _pipeline_wiring_guideline_message(pipeline_type: str) -> str:
    """Return a short wiring guideline message for the given pipeline type (text from normalizer.system_comments)."""
    if pipeline_type == "RLOracle":
        return f"{PIPELINE_WIRING_PREFIX_RLORACLE} {PIPELINE_WIRING_BASE}"
    if pipeline_type == RL_GYM_NODE_TYPE:  # "RLGym"
        return f"{PIPELINE_WIRING_PREFIX_RLGYM} {PIPELINE_WIRING_BASE}"
    if pipeline_type == "RLSet":
        return f"{PIPELINE_WIRING_PREFIX_RLAGENT} {PIPELINE_WIRING_BASE}"
    if pipeline_type == "LLMSet":
        return f"{PIPELINE_WIRING_PREFIX_LLMAGENT} {PIPELINE_WIRING_BASE}"
    return f"{pipeline_type} Pipeline Wiring Guidelines! {PIPELINE_WIRING_BASE}"

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
    """Unit payload for add_unit: a single graph unit (Source, Valve, Tank, Sensor, RLAgent, LLMAgent, etc.)."""

    id: str = Field(..., description="Unique unit identifier")
    type: str = Field(..., description="Unit type: Source, Valve, Tank, Sensor, RLAgent, LLMAgent, etc.")
    controllable: bool = Field(default=False, description="Whether this unit is an action/control input")
    params: dict[str, Any] = Field(default_factory=dict, description="Type-specific parameters")
    name: str | None = Field(default=None, description="Optional display name for the unit")


class GraphEditPipeline(BaseModel):
    """Pipeline payload for add_pipeline: RLGym, RLOracle, RLSet, or LLMSet (training/serving pipeline, not a single unit)."""

    id: str = Field(..., description="Unique pipeline identifier (e.g. rl_training, ai_student, my_rl_agent, my_llm_agent)")
    type: str = Field(..., description="Pipeline type: RLGym, RLOracle, RLSet, or LLMSet")
    params: dict[str, Any] = Field(default_factory=dict, description="observation_source_ids, action_target_ids, adapter_config, max_steps (RLGym/RLOracle); inference_url, model_path (RLSet); model_name, provider, system_prompt (LLMSet), etc.")


class GraphEdit(BaseModel):
    """Structured graph edit from Process Assistant (validate in backend)."""

    action: GraphEditAction = Field(
        ...,
        description="add_unit | add_pipeline | remove_unit | connect | disconnect | no_edit | replace_graph | replace_unit | add_code_block | add_comment | add_todo_list | remove_todo_list | add_task | remove_task | mark_completed | add_environment | import_unit | import_workflow",
    )
    unit_id: str | None = Field(default=None, description="For remove_unit")
    unit: GraphEditUnit | None = Field(default=None, description="For add_unit: single graph unit (process, RLAgent, LLMAgent)")
    pipeline: GraphEditPipeline | None = Field(default=None, description="For add_pipeline: RLGym or RLOracle pipeline (not a unit)")
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
    # add_comment: assistant note on the flow (stored in graph comments metadata; not exported to external runtimes)
    info: str | None = Field(default=None, description="For add_comment: comment text")
    commenter: str | None = Field(default=None, description="For add_comment: optional identifier of who left the comment (e.g. assistant name)")
    # Todo list actions (graph metadata; not exported to runtimes)
    title: str | None = Field(default=None, description="For add_todo_list: optional list title")
    task_id: str | None = Field(default=None, description="For remove_task, mark_completed: task id")
    text: str | None = Field(default=None, description="For add_task: task description")
    completed: bool = Field(default=True, description="For mark_completed: set completed (default true)")
    # add_environment: add an environment to the graph so env-specific units become available in the Units Library
    env_id: str | None = Field(default=None, description="For add_environment: environment id (e.g. thermodynamic, data_bi)")

    model_config = {"populate_by_name": True}


def _normalize_edit(edit: dict[str, Any]) -> dict[str, Any]:
    """If edit has units+connections but no action, treat as replace_graph."""
    if edit.get("action") is not None:
        return dict(edit)
    if isinstance(edit.get("units"), list) and isinstance(edit.get("connections"), list):
        return {**edit, "action": "replace_graph"}
    return dict(edit)


def _language_for_origin(origin: dict[str, Any] | None) -> str | None:
    """Return expected code language from origin (runtime); uses centralized runtime_detector."""
    if not origin or not isinstance(origin, dict):
        return None
    rt = runtime_label({"origin": origin})
    return _ORIGIN_LANGUAGE.get(rt)


# Canonical topology unit ids (created automatically when adding RLAgent/LLMAgent or RLOracle)
_CANONICAL_JOIN_ID = "collector"
_CANONICAL_SWITCH_ID = "switch"
_CANONICAL_STEP_DRIVER_ID = "step_driver"
_CANONICAL_SPLIT_ID = "split"
_CANONICAL_STEP_REWARDS_ID = "step_rewards"
_CANONICAL_HTTP_IN_ID = "http_in"
_CANONICAL_HTTP_RESPONSE_ID = "http_response"
# Front switch (same type as Switch): 1 input from http_in, 2 outputs: 0 → step_driver, 1 → switch (action demux)
_CANONICAL_STEP_ROUTER_ID = "step_router"

# Start port index for simulator units (Split output -> unit start input)
_START_PORT_BY_TYPE: dict[str, str] = {"Source": "0", "Tank": "5"}


def _ensure_canonical_topology(
    units: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    obs_ids: list[str],
    act_ids: list[str],
    *,
    include_training_units: bool = True,
    include_http_endpoints: bool = False,
) -> None:
    """Ensure canonical units exist and are wired.
    - include_training_units=True (e.g. RLGym): Join, Switch, StepDriver, Split, StepRewards (full training).
    - include_training_units=False (e.g. RLAgent/LLMAgent): Join, Switch only (short: obs -> Join -> Agent -> Switch -> actions).
    - include_http_endpoints: add http_in, step_router, http_response only when True (external access)."""
    # Env-agnostic units (canonical + RLAgent/LLMAgent/RLGym/RLOracle) so they exist when adding from GUI or any env
    try:
        from units.register_env_agnostic import register_env_agnostic_units
        register_env_agnostic_units()
    except Exception:
        return
    type_join = get_type_by_role("join")
    type_switch = get_type_by_role("switch")
    type_step_driver = get_type_by_role("step_driver")
    type_step_rewards = get_type_by_role("step_rewards")
    type_split = get_type_by_role("split")
    type_http_in = get_type_by_role("http_in")
    type_http_response = get_type_by_role("http_response")
    if not type_join or not type_switch or not type_step_driver:
        return  # registry not loaded or roles missing

    unit_ids = {x.get("id") for x in units if isinstance(x, dict) and x.get("id")}
    unit_by_id = {x.get("id"): x for x in units if isinstance(x, dict) and x.get("id")}

    # Join: obs sources -> collector in_0, in_1, ...
    if _CANONICAL_JOIN_ID not in unit_ids:
        units.append({
            "id": _CANONICAL_JOIN_ID,
            "type": type_join,
            "controllable": False,
            "params": {"num_inputs": max(len(obs_ids), 1)},
        })
        unit_ids.add(_CANONICAL_JOIN_ID)
        for i, sid in enumerate(sorted(obs_ids)):
            if sid in unit_ids:
                connections.append({"from": sid, "to": _CANONICAL_JOIN_ID, "from_port": "0", "to_port": str(i)})

    # Switch: switch out_0, out_1, ... -> action targets (first input port)
    if _CANONICAL_SWITCH_ID not in unit_ids:
        units.append({
            "id": _CANONICAL_SWITCH_ID,
            "type": type_switch,
            "controllable": False,
            "params": {"num_outputs": max(len(act_ids), 1)},
        })
        unit_ids.add(_CANONICAL_SWITCH_ID)
        for i, tid in enumerate(sorted(act_ids)):
            if tid in unit_ids:
                connections.append({"from": _CANONICAL_SWITCH_ID, "to": tid, "from_port": str(i), "to_port": "0"})

    # Full training topology (RLGym): StepDriver, Split, StepRewards. Omit for short topology (RLAgent/LLMAgent only).
    if include_training_units:
        # StepDriver
        if _CANONICAL_STEP_DRIVER_ID not in unit_ids:
            units.append({
                "id": _CANONICAL_STEP_DRIVER_ID,
                "type": type_step_driver,
                "controllable": False,
                "params": {},
            })
            unit_ids.add(_CANONICAL_STEP_DRIVER_ID)

        # Split: step_driver out 0 -> split in 0; split out_i -> simulator i (start port). Always add Split when training units are included so topology is complete (wire to simulators when present).
        simulator_ids = [
            uid for uid in unit_ids
            if (unit_by_id.get(uid) or {}).get("type") in ("Source", "Tank")
        ]
        if _CANONICAL_SPLIT_ID not in unit_ids and type_split:
            units.append({
                "id": _CANONICAL_SPLIT_ID,
                "type": type_split,
                "controllable": False,
                "params": {"num_outputs": max(len(simulator_ids), 1)},
            })
            unit_ids.add(_CANONICAL_SPLIT_ID)
            connections.append({"from": _CANONICAL_STEP_DRIVER_ID, "to": _CANONICAL_SPLIT_ID, "from_port": "0", "to_port": "0"})
            for i, sim_id in enumerate(sorted(simulator_ids)):
                u = unit_by_id.get(sim_id)
                to_port = _START_PORT_BY_TYPE.get((u or {}).get("type", ""), "0")
                connections.append({"from": _CANONICAL_SPLIT_ID, "to": sim_id, "from_port": str(i), "to_port": to_port})

        # StepRewards: Join → observation; StepDriver → trigger (executor also injects trigger when no connection).
        if type_step_rewards and _CANONICAL_JOIN_ID in unit_ids:
            if _CANONICAL_STEP_REWARDS_ID not in unit_ids:
                units.append({
                    "id": _CANONICAL_STEP_REWARDS_ID,
                    "type": type_step_rewards,
                    "controllable": False,
                    "params": {"max_steps": 600},
                })
                unit_ids.add(_CANONICAL_STEP_REWARDS_ID)
            connections.append({"from": _CANONICAL_JOIN_ID, "to": _CANONICAL_STEP_REWARDS_ID, "from_port": "observation", "to_port": "observation"})
            if _CANONICAL_STEP_DRIVER_ID in unit_ids:
                connections.append({"from": _CANONICAL_STEP_DRIVER_ID, "to": _CANONICAL_STEP_REWARDS_ID, "from_port": "2", "to_port": "1"})

    # HTTP endpoints (opt-in only): user adds when they want external access. Not part of standard wiring.
    if include_http_endpoints and type_http_in and type_http_response:
        if _CANONICAL_HTTP_IN_ID not in unit_ids:
            units.append({
                "id": _CANONICAL_HTTP_IN_ID,
                "type": type_http_in,
                "controllable": False,
                "params": {},
            })
            unit_ids.add(_CANONICAL_HTTP_IN_ID)
        if _CANONICAL_STEP_ROUTER_ID not in unit_ids:
            units.append({
                "id": _CANONICAL_STEP_ROUTER_ID,
                "type": type_switch,
                "controllable": False,
                "params": {"num_outputs": 2},
            })
            unit_ids.add(_CANONICAL_STEP_ROUTER_ID)
        if _CANONICAL_HTTP_RESPONSE_ID not in unit_ids:
            units.append({
                "id": _CANONICAL_HTTP_RESPONSE_ID,
                "type": type_http_response,
                "controllable": False,
                "params": {},
            })
            unit_ids.add(_CANONICAL_HTTP_RESPONSE_ID)
        # http_in output 0 → step_router (front switch) input 0
        connections.append({"from": _CANONICAL_HTTP_IN_ID, "to": _CANONICAL_STEP_ROUTER_ID, "from_port": "0", "to_port": "0"})
        # step_router output 0 → step_driver input 0; output 1 → switch (action demux) input 0
        connections.append({"from": _CANONICAL_STEP_ROUTER_ID, "to": _CANONICAL_STEP_DRIVER_ID, "from_port": "0", "to_port": "0"})
        connections.append({"from": _CANONICAL_STEP_ROUTER_ID, "to": _CANONICAL_SWITCH_ID, "from_port": "1", "to_port": "0"})
        # step response: StepRewards.payload → http_response (when present); else step_driver output 1 → http_response
        if _CANONICAL_STEP_REWARDS_ID in unit_ids:
            connections.append({"from": _CANONICAL_STEP_REWARDS_ID, "to": _CANONICAL_HTTP_RESPONSE_ID, "from_port": "payload", "to_port": "payload"})
        else:
            connections.append({"from": _CANONICAL_STEP_DRIVER_ID, "to": _CANONICAL_HTTP_RESPONSE_ID, "from_port": "1", "to_port": "0"})


def _ensure_unit_ports_from_registry(unit: dict[str, Any]) -> None:
    """Set unit's input_ports and output_ports from registry (Registry → Graph). Mutates unit in place."""
    if not isinstance(unit, dict) or unit.get("id") is None:
        return
    spec = get_unit_spec(str(unit.get("type", "")))
    if spec is not None:
        unit["input_ports"] = [{"name": n, "type": t or None} for n, t in spec.input_ports]
        unit["output_ports"] = [{"name": n, "type": t or None} for n, t in spec.output_ports]
    elif unit.get("input_ports") is None or unit.get("output_ports") is None:
        unit.setdefault("input_ports", [])
        unit.setdefault("output_ports", [])


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

    if parsed.action == "add_environment":
        env_id_raw = (parsed.env_id or edit.get("id") or "").strip().lower()
        if not env_id_raw:
            raise ValueError("add_environment requires env_id (e.g. thermodynamic, data_bi)")
        from units.env_loaders import known_environment_tags
        known = known_environment_tags()
        if env_id_raw not in known:
            raise ValueError(f"Unknown environment: {env_id_raw!r}. Known: {sorted(known)}")
        cur = current.get("environments") or []
        result = dict(current)
        result["environments"] = sorted(set(cur) | {env_id_raw})
        return result

    add_code_block_payload: dict[str, Any] | None = None
    add_oracle_code_blocks: list[dict[str, Any]] = []
    add_pyflow_code_blocks: list[dict[str, Any]] = []
    add_node_red_code_blocks: list[dict[str, Any]] = []
    add_n8n_code_blocks: list[dict[str, Any]] = []
    comments: list[dict[str, Any]] = list(current.get("comments") or [])
    todo_list: dict[str, Any] | None = current.get("todo_list")
    if todo_list is not None and not isinstance(todo_list, dict):
        todo_list = None
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
            if c.get("connection_type") is not None:
                conn["connection_type"] = str(c["connection_type"])
            connections.append(conn)

    # Validate and normalize: pipeline types (LLMSet, RLSet, RLGym, RLOracle) must use add_pipeline;
    # graph unit types (RLAgent, LLMAgent) must use add_unit. Normalize add_unit with pipeline type → add_pipeline.
    if (parsed.action == "add_pipeline" and parsed.pipeline is not None) or (
        parsed.action == "add_unit"
        and parsed.unit is not None
        and getattr(parsed.unit, "type", None) in PIPELINE_TYPES
    ):
        if parsed.action == "add_pipeline":
            p = parsed.pipeline
        else:
            u = parsed.unit
            p = GraphEditPipeline(
                id=u.id,
                type=u.type,
                params=dict(u.params) if u.params else {},
            )
        if p.type in RL_AGENT_NODE_TYPES or p.type in LLM_AGENT_NODE_TYPES:
            raise ValueError(
                WORKFLOW_DESIGNER_ADD_PIPELINE_USE_ADD_UNIT_ERROR.format(unit_type=p.type)
            )
        if p.type not in PIPELINE_TYPES:
            raise ValueError(
                WORKFLOW_DESIGNER_ADD_PIPELINE_REQUIRED_TYPES_ERROR.format(unit_type=p.type)
            )
        if any(x["id"] == p.id for x in units):
            raise ValueError(f"Unit id already exists: {p.id}")
        if p.type == RL_GYM_NODE_TYPE:
            # Full training setup for our runtime: Join, StepRewards, Switch, StepDriver, Split.
            if get_unit_spec(RL_GYM_NODE_TYPE) is None:
                try:
                    from units.pipelines.rl_gym import register_rl_gym
                    register_rl_gym()
                except Exception:
                    pass
            obs_ids = p.params.get("observation_source_ids")
            act_ids = p.params.get("action_target_ids")
            if isinstance(obs_ids, list):
                obs_ids = [str(x) for x in obs_ids]
            else:
                obs_ids = []
            if isinstance(act_ids, list):
                act_ids = [str(x) for x in act_ids]
            else:
                act_ids = []
            _ensure_canonical_topology(units, connections, obs_ids, act_ids, include_training_units=True)
            units.append({
                "id": p.id,
                "type": RL_GYM_NODE_TYPE,
                "controllable": False,
                "params": {k: v for k, v in (p.params or {}).items()},
            })
        elif p.type == "RLOracle":
            adapter_config = dict(p.params.get("adapter_config") or p.params)
            origin = current.get("origin") or {}
            lang = _language_for_origin(origin) or "python"
            obs_ids = (
                p.params.get("observation_source_ids")
                or adapter_config.get("observation_sources")
                or adapter_config.get("observation_source_ids")
            )
            act_ids = (
                p.params.get("action_target_ids")
                or adapter_config.get("action_target_ids")
                or adapter_config.get("action_targets")
            )
            if isinstance(obs_ids, list):
                obs_ids = [str(x) for x in obs_ids]
            else:
                obs_ids = []
            if isinstance(act_ids, list):
                act_ids = [str(x) for x in act_ids]
            else:
                act_ids = []
            adapter_config["observation_source_ids"] = obs_ids
            adapter_config["action_target_ids"] = act_ids
            _ensure_canonical_topology(units, connections, obs_ids, act_ids, include_http_endpoints=True)
            cbs = render_oracle_code_blocks_for_canonical(
                adapter_config,
                language=lang,
                observation_source_ids=obs_ids or None,
                n8n_mode=(runtime_label(current) == "n8n"),
            )
            add_oracle_code_blocks.extend(cbs)
        elif p.type == "RLSet":
            # Full RL agent set: Join, Switch, RLAgent unit, wiring, code blocks. Same params as RLAgent unit.
            obs_ids = p.params.get("observation_source_ids")
            act_ids = p.params.get("action_target_ids")
            if isinstance(obs_ids, list):
                obs_ids = [str(x) for x in obs_ids]
            else:
                obs_ids = []
            if isinstance(act_ids, list):
                act_ids = [str(x) for x in act_ids]
            else:
                act_ids = []
            _ensure_canonical_topology(units, connections, obs_ids, act_ids, include_training_units=False)
            model_path = p.params.get("model_path", "")
            inference_url = str(p.params.get("inference_url") or "http://127.0.0.1:8000/predict")
            units.append({
                "id": p.id,
                "type": "RLAgent",
                "controllable": False,
                "params": {"model_path": model_path, **{k: v for k, v in (p.params or {}).items() if k not in ("observation_source_ids", "action_target_ids")}},
            })
            connections.append({"from": _CANONICAL_JOIN_ID, "to": p.id, "from_port": "0", "to_port": "0"})
            connections.append({"from": p.id, "to": _CANONICAL_SWITCH_ID, "from_port": "0", "to_port": "0"})
            origin = current.get("origin") or {}
            lang = _language_for_origin(origin) or "python"
            if lang == "python":
                code_src = render_rl_agent_predict_py(inference_url, obs_ids if obs_ids else [])
                add_oracle_code_blocks.append({"id": p.id, "language": "python", "source": code_src})
            elif runtime_label(current) == "n8n":
                code_src = render_rl_agent_predict_n8n(inference_url, obs_ids if obs_ids else [])
                add_oracle_code_blocks.append({"id": p.id, "language": "javascript", "source": code_src})
            else:
                code_src = render_rl_agent_predict_js(inference_url, obs_ids if obs_ids else [])
                add_oracle_code_blocks.append({"id": p.id, "language": "javascript", "source": code_src})
        elif p.type == "LLMSet":
            # Full LLM agent set: Join, Switch, LLMAgent unit, wiring, code blocks. Same params as LLMAgent unit.
            obs_ids = p.params.get("observation_source_ids")
            act_ids = p.params.get("action_target_ids")
            if isinstance(obs_ids, list):
                obs_ids = [str(x) for x in obs_ids]
            else:
                obs_ids = []
            if isinstance(act_ids, list):
                act_ids = [str(x) for x in act_ids]
            else:
                act_ids = []
            _ensure_canonical_topology(units, connections, obs_ids, act_ids, include_training_units=False)
            inference_url = str(p.params.get("inference_url") or "http://127.0.0.1:8001/predict")
            system_prompt = str(p.params.get("system_prompt") or "You are a control agent. Given observations, output a JSON object with an 'action' key containing a list of numbers.")
            user_prompt_template = str(p.params.get("user_prompt_template") or "Observations: {observation_json}. Output only a JSON object with key 'action' and value a list of numbers.")
            model_name = str(p.params.get("model_name") or "llama3.2")
            provider = str(p.params.get("provider") or "ollama")
            host = str(p.params.get("host") or "")
            llm_params = {k: v for k, v in (p.params or {}).items() if k not in ("observation_source_ids", "action_target_ids")}
            units.append({
                "id": p.id,
                "type": "LLMAgent",
                "controllable": False,
                "params": llm_params,
            })
            connections.append({"from": _CANONICAL_JOIN_ID, "to": p.id, "from_port": "0", "to_port": "0"})
            connections.append({"from": p.id, "to": _CANONICAL_SWITCH_ID, "from_port": "0", "to_port": "0"})
            origin = current.get("origin") or {}
            lang = _language_for_origin(origin) or "python"
            if lang == "python":
                code_src = render_llm_agent_predict_py(
                    inference_url, obs_ids if obs_ids else [],
                    system_prompt, user_prompt_template, model_name, provider, host,
                )
                add_oracle_code_blocks.append({"id": p.id, "language": "python", "source": code_src})
            elif runtime_label(current) == "n8n":
                code_src = render_llm_agent_predict_n8n(
                    inference_url, obs_ids if obs_ids else [],
                    system_prompt, user_prompt_template, model_name, provider, host,
                )
                add_oracle_code_blocks.append({"id": p.id, "language": "javascript", "source": code_src})
            else:
                code_src = render_llm_agent_predict_js(
                    inference_url, obs_ids if obs_ids else [],
                    system_prompt, user_prompt_template, model_name, provider, host,
                )
                add_oracle_code_blocks.append({"id": p.id, "language": "javascript", "source": code_src})
        # System comment with wiring guidelines when any canonical pipeline is added
        comment_id = "comment_" + uuid4().hex[:8]
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        comments.append({
            "id": comment_id,
            "info": _pipeline_wiring_guideline_message(p.type),
            "commenter": "system",
            "created_at": created_at,
        })

    elif parsed.action == "add_unit" and parsed.unit is not None:
        u = parsed.unit
        if any(x["id"] == u.id for x in units):
            raise ValueError(f"Unit id already exists: {u.id}")
        # Type must be in Units Library (registry) unless coding_is_allowed
        if get_unit_spec(u.type) is None and not _coding_is_allowed():
            raise ValueError("Invalid unit. Use units from the Units Library.")
        if u.type in RL_AGENT_NODE_TYPES:
            model_path = u.params.get("model_path", "")
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
            _ensure_canonical_topology(units, connections, obs_ids or [], act_ids or [], include_training_units=False)
            inference_url = str(u.params.get("inference_url") or "http://127.0.0.1:8000/predict")
            units.append({
                "id": u.id,
                "type": u.type,
                "controllable": False,
                "params": {"model_path": model_path, **{k: v for k, v in u.params.items() if k not in ("observation_source_ids", "action_target_ids")}},
            })
            connections.append({"from": _CANONICAL_JOIN_ID, "to": u.id, "from_port": "0", "to_port": "0"})
            connections.append({"from": u.id, "to": _CANONICAL_SWITCH_ID, "from_port": "0", "to_port": "0"})
            origin = current.get("origin") or {}
            lang = _language_for_origin(origin) or "python"
            if lang == "python":
                code_src = render_rl_agent_predict_py(inference_url, obs_ids if obs_ids else [])
                add_oracle_code_blocks.append({"id": u.id, "language": "python", "source": code_src})
            elif runtime_label(current) == "n8n":
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
            _ensure_canonical_topology(units, connections, obs_ids or [], act_ids or [], include_training_units=False)
            inference_url = str(u.params.get("inference_url") or "http://127.0.0.1:8001/predict")
            system_prompt = str(u.params.get("system_prompt") or "You are a control agent. Given observations, output a JSON object with an 'action' key containing a list of numbers.")
            user_prompt_template = str(u.params.get("user_prompt_template") or "Observations: {observation_json}. Output only a JSON object with key 'action' and value a list of numbers.")
            model_name = str(u.params.get("model_name") or "llama3.2")
            provider = str(u.params.get("provider") or "ollama")
            host = str(u.params.get("host") or "")
            llm_params = {k: v for k, v in u.params.items() if k not in ("observation_source_ids", "action_target_ids")}
            units.append({
                "id": u.id,
                "type": u.type,
                "controllable": False,
                "params": llm_params,
            })
            connections.append({"from": _CANONICAL_JOIN_ID, "to": u.id, "from_port": "0", "to_port": "0"})
            connections.append({"from": u.id, "to": _CANONICAL_SWITCH_ID, "from_port": "0", "to_port": "0"})
            origin = current.get("origin") or {}
            lang = _language_for_origin(origin) or "python"
            if lang == "python":
                code_src = render_llm_agent_predict_py(
                    inference_url, obs_ids if obs_ids else [],
                    system_prompt, user_prompt_template, model_name, provider, host,
                )
                add_oracle_code_blocks.append({"id": u.id, "language": "python", "source": code_src})
            elif runtime_label(current) == "n8n":
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
            add_u: dict[str, Any] = {
                "id": u.id,
                "type": u.type,
                "controllable": u.controllable,
                "params": dict(u.params),
            }
            if u.name is not None and str(u.name).strip():
                add_u["name"] = str(u.name).strip()
            units.append(add_u)
            # PyFlow catalog: when assistant adds a unit of a PyFlow type, attach template as code_block
            if u.type in get_pyflow_types():
                entry = get_pyflow_template(u.type)
                if entry and entry.get("code_template"):
                    add_pyflow_code_blocks.append({
                        "id": u.id,
                        "language": "python",
                        "source": entry["code_template"],
                    })
            # Node-RED catalog: when graph is node_red and unit type is in catalog, attach JS template for export
            if runtime_label(current) == "node_red" and u.type in get_node_red_types():
                entry = get_node_red_template(u.type)
                if entry and entry.get("code_template"):
                    add_node_red_code_blocks.append({
                        "id": u.id,
                        "language": "javascript",
                        "source": entry["code_template"],
                    })
            # n8n catalog: when graph is n8n and unit type is in catalog, attach JS template for export
            if runtime_label(current) == "n8n" and u.type in get_n8n_types():
                entry = get_n8n_template(u.type)
                if entry and entry.get("code_template"):
                    add_n8n_code_blocks.append({
                        "id": u.id,
                        "language": "javascript",
                        "source": entry["code_template"],
                    })

    elif parsed.action == "remove_unit":
        if parsed.unit_id is None:
            raise ValueError("Incorrect format for remove_unit: missing required parameter: unit_id")
        uid = parsed.unit_id
        to_remove: set[str] = {uid}
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
        new_u: dict[str, Any] = {
            "id": new_id,
            "type": new_unit.type,
            "controllable": new_unit.controllable,
            "params": dict(new_unit.params),
        }
        if new_unit.name is not None and str(new_unit.name).strip():
            new_u["name"] = str(new_unit.name).strip()
        units.append(new_u)
        # Reconnect: replace old_id with new_id in all connections
        for c in connections:
            if c.get("from") == old_id:
                c["from"] = new_id
            if c.get("to") == old_id:
                c["to"] = new_id

    elif parsed.action == "add_code_block":
        if not _coding_is_allowed():
            raise ValueError("Invalid unit. Use units from the Units Library.")
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

    elif parsed.action == "add_comment":
        if not parsed.info or not str(parsed.info).strip():
            raise ValueError("Incorrect format for add_comment: missing required parameter: info (non-empty string)")
        comment_id = "comment_" + uuid4().hex[:8]
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        comments.append({
            "id": comment_id,
            "info": str(parsed.info).strip(),
            "commenter": str(parsed.commenter).strip() if parsed.commenter and str(parsed.commenter).strip() else "",
            "created_at": created_at,
        })

    elif parsed.action == "add_todo_list":
        todo_list = todo_ensure_list(todo_list)
        if parsed.title is not None and str(parsed.title).strip():
            todo_list = {**todo_list, "title": str(parsed.title).strip()}

    elif parsed.action == "remove_todo_list":
        todo_list = None

    elif parsed.action == "add_task":
        if not parsed.text or not str(parsed.text).strip():
            raise ValueError("Incorrect format for add_task: missing required parameter: text (non-empty string)")
        todo_list = todo_ensure_list(todo_list)
        todo_list = todo_add_task(todo_list, str(parsed.text).strip())

    elif parsed.action == "remove_task":
        if not parsed.task_id or not str(parsed.task_id).strip():
            raise ValueError("Incorrect format for remove_task: missing required parameter: task_id")
        todo_list = todo_ensure_list(todo_list)
        todo_list = todo_remove_task(todo_list, str(parsed.task_id).strip())

    elif parsed.action == "mark_completed":
        if not parsed.task_id or not str(parsed.task_id).strip():
            raise ValueError("Incorrect format for mark_completed: missing required parameter: task_id")
        todo_list = todo_ensure_list(todo_list)
        todo_list = todo_mark_completed(todo_list, str(parsed.task_id).strip(), completed=parsed.completed)

    elif parsed.action == "replace_graph" and parsed.units is not None and parsed.connections is not None:
        # Full graph replacement: normalize unit/connection dicts to have id, type, controllable, params / from, to; optional name
        units = []
        for u in parsed.units:
            if isinstance(u, dict):
                unit_entry: dict[str, Any] = {
                    "id": str(u.get("id", "")),
                    "type": str(u.get("type", "Unit")),
                    "controllable": bool(u.get("controllable", False)),
                    "params": dict(u.get("params", {})),
                }
                if u.get("name") is not None and str(u.get("name", "")).strip():
                    unit_entry["name"] = str(u["name"]).strip()
                units.append(unit_entry)
        connections = []
        for c in parsed.connections:
            if isinstance(c, dict):
                from_id = c.get("from") or c.get("from_id")
                to_id = c.get("to") or c.get("to_id")
                if from_id is not None and to_id is not None:
                    conn: dict[str, Any] = {
                        "from": str(from_id),
                        "to": str(to_id),
                        "from_port": str(c.get("from_port", "0")),
                        "to_port": str(c.get("to_port", "0")),
                    }
                    if c.get("connection_type") is not None:
                        conn["connection_type"] = str(c["connection_type"])
                    connections.append(conn)

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
    code_blocks.extend(add_pyflow_code_blocks)
    code_blocks.extend(add_node_red_code_blocks)
    code_blocks.extend(add_n8n_code_blocks)
    layout = dict(current.get("layout") or {})
    if parsed.action == "replace_unit" and parsed.find_unit and parsed.replace_with:
        old_id, new_id = parsed.find_unit.id, parsed.replace_with.id
        if old_id in layout and new_id not in layout:
            layout[new_id] = layout[old_id]
    layout = {k: v for k, v in layout.items() if k in final_unit_ids}

    # Registry → Graph: ensure every unit has input_ports and output_ports from registry
    for u in units:
        if isinstance(u, dict):
            _ensure_unit_ports_from_registry(u)

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
    if current.get("environments") is not None:
        result["environments"] = current["environments"]
    if current.get("origin") is not None:
        result["origin"] = current["origin"]
    if comments:
        result["comments"] = comments
    if todo_list is not None:
        result["todo_list"] = todo_list
    elif "todo_list" in current:
        result["todo_list"] = None
    return result
