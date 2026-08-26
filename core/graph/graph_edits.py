"""
Graph edit schema and apply logic for Process agent.
Edits are applied to a graph dict; then normalizer.to_process_graph(updated) yields canonical ProcessGraph.
"""

import datetime
import json
from pathlib import Path
from typing import ClassVar, Literal, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from core.graph.pipeline_templates import (
    load_pipeline_template,
    merge_pipeline_into_graph,
)
from core.graph.todo_list import (
    normalize_todo_lists,
    todo_lists_to_list,
)
from core.normalizer.runtime_detector import runtime_label
from core.normalizer.system_comments import (
    PIPELINE_WIRING_BASE,
    PIPELINE_WIRING_LLMAGENT,
    PIPELINE_WIRING_PREFIX_LLMAGENT,
    PIPELINE_WIRING_PREFIX_RLAGENT,
    PIPELINE_WIRING_PREFIX_RLGYM,
    PIPELINE_WIRING_PREFIX_RLORACLE,
)
from core.schemas import TodoList
from core.schemas.agent_node import (
    LLM_AGENT_NODE_TYPES,
    RL_AGENT_NODE_TYPES,
    RL_GYM_NODE_TYPE,
)
from deploy.agent_inject import (
    render_llm_agent_predict_js,
    render_llm_agent_predict_n8n,
    render_llm_agent_predict_py,
    render_rl_agent_predict_js,
    render_rl_agent_predict_n8n,
    render_rl_agent_predict_py,
)
from deploy.oracle_inject import render_oracle_code_blocks_for_canonical
from runtime.control_queue_protocol import JsonValue
from units.n8n import get_n8n_template, get_n8n_types
from units.node_red import get_node_red_template, get_node_red_types
from units.pyflow import get_pyflow_template, get_pyflow_types
from units.registry import get_type_by_role, get_unit_spec

# App setting: coding_is_allowed (read from config/app_settings.json so graph_edits has no gui dependency)
_CODING_IS_ALLOWED_KEY = "coding_is_allowed"
_CODING_IS_ALLOWED_DEFAULT = False

type JSONValue = (
    None
    | bool
    | int
    | float
    | str
    | list[JSONValue]
    | dict[str, JSONValue]
)

def _coding_is_allowed() -> bool:
    """Return whether coding is enabled in app_settings.json."""
    try:
        repo_root = Path(__file__).resolve().parent.parent.parent
        config_path = repo_root / "config" / "app_settings.json"

        if not config_path.is_file():
            return _CODING_IS_ALLOWED_DEFAULT

        raw_data = cast(
            object,
            json.loads(config_path.read_text(encoding="utf-8")),
        )

        if not isinstance(raw_data, dict):
            return _CODING_IS_ALLOWED_DEFAULT

        data = cast(dict[str, JSONValue], raw_data)
        raw_value = data.get(_CODING_IS_ALLOWED_KEY)

        if isinstance(raw_value, bool):
            return raw_value

        return _CODING_IS_ALLOWED_DEFAULT

    except (OSError, json.JSONDecodeError):
        return _CODING_IS_ALLOWED_DEFAULT


def is_coding_allowed_from_app_settings() -> bool:
    """Same value as GUI `get_coding_is_allowed()`; for Units Library and other non-GUI callers."""
    return _coding_is_allowed()


# Unit types that use graph code_blocks / custom source; omitted from Units Library prompt when coding is off.
_CUSTOM_CODE_UNIT_TYPES = frozenset({"function", "exec", "script"})


def _reject_custom_code_unit_if_disabled(unit_type: str) -> None:
    if _coding_is_allowed():
        return
    if (unit_type or "").strip().lower() in _CUSTOM_CODE_UNIT_TYPES:
        raise ValueError(
            "Custom code units (function / exec / script) are disabled. "
            + "Enable 'allow custom code' in app settings or use other unit types from the Units Library."
        )


# Action types
GraphEditAction = Literal[
    "add_unit",
    "add_pipeline",
    "remove_unit",
    "set_params",
    "connect",
    "disconnect",
    "no_edit",
    "replace_graph",
    "replace_unit",
    "add_code_block",
    "add_comment",
    "remove_comment",
    "add_todo_list",
    "remove_todo_list",
    "add_task",
    "remove_task",
    "set_implementer",
    "set_deadline",
    "set_curator",
    "set_todo_list_title",
    "mark_completed",
    "add_environment",
    "import_workflow",
]

# Pipeline types: RLGym, RLOracle, RLSet, LLMSet. Not graph "units" — they describe a training/serving pipeline.
# Use add_pipeline with "pipeline" payload. Unit types (Source, Valve, RLAgent, LLMAgent, etc.) use add_unit.
PIPELINE_TYPES: frozenset[str] = frozenset(
    [RL_GYM_NODE_TYPE, "RLOracle", "RLSet", "LLMSet"]
)


def _pipeline_wiring_guideline_message(pipeline_type: str) -> str:
    """Return a short wiring guideline message for the given pipeline type (text from normalizer.system_comments)."""
    if pipeline_type == "RLOracle":
        return f"{PIPELINE_WIRING_PREFIX_RLORACLE} {PIPELINE_WIRING_BASE}"
    if pipeline_type == RL_GYM_NODE_TYPE:  # "RLGym"
        return f"{PIPELINE_WIRING_PREFIX_RLGYM} {PIPELINE_WIRING_BASE}"
    if pipeline_type == "RLSet":
        return f"{PIPELINE_WIRING_PREFIX_RLAGENT} {PIPELINE_WIRING_BASE}"
    if pipeline_type == "LLMSet":
        return f"{PIPELINE_WIRING_PREFIX_LLMAGENT} {PIPELINE_WIRING_LLMAGENT}"
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
    language: str = Field(
        ..., description="Language: javascript (Node-RED/n8n), python (PyFlow/Ryven)"
    )
    source: str = Field(default="", description="Raw source code")


class GraphEditUnit(BaseModel):
    """Unit payload for add_unit: a single graph unit (Source, Valve, Tank, Sensor, RLAgent, LLMAgent, etc.)."""

    id: str = Field(..., description="Unique unit identifier")
    type: str = Field(
        ...,
        description="Unit type: Source, Valve, Tank, Sensor, RLAgent, LLMAgent, etc.",
    )
    controllable: bool = Field(
        default=False, description="Whether this unit is an action/control input"
    )
    params: dict[str, JSONValue] = Field(
        default_factory=dict, description="Type-specific parameters"
    )
    name: str | None = Field(
        default=None, description="Optional display name for the unit"
    )


class GraphEditPipeline(BaseModel):
    """Pipeline payload for add_pipeline: RLGym, RLOracle, RLSet, or LLMSet (training/serving pipeline, not a single unit)."""

    id: str = Field(
        ...,
        description="Unique pipeline identifier (e.g. rl_training, ai_student, my_rl_agent, my_llm_agent)",
    )
    type: str = Field(
        ..., description="Pipeline type: RLGym, RLOracle, RLSet, or LLMSet"
    )
    params: dict[str, JSONValue] = Field(
        default_factory=dict,
        description="observation_source_ids, action_target_ids, adapter_config, max_steps (RLGym/RLOracle); inference_url, model_path (RLSet); model_name, provider, system_prompt (LLMSet), etc.",
    )


class GraphEdit(BaseModel):
    """Structured graph edit from Process agent (validate in backend)."""

    action: GraphEditAction = Field(
        ...,
        description=(
                    "add_unit | add_pipeline | remove_unit | set_params | connect | disconnect | no_edit | "
                    "replace_graph | replace_unit | add_code_block | add_comment | add_todo_list | "
                    "remove_todo_list | add_task | remove_task | mark_completed | set_implementer | "
                    "set_deadline | set_curator | add_environment | import_workflow"
                ),
            )
    unit_id: str | None = Field(default=None, description="For remove_unit")
    id: str | None = Field(
        default=None, description="For set_params: unit id to update"
    )
    new_params: dict[str, JSONValue] | None = Field(
        default=None,
        description="For set_params: params to set (merged into unit params)",
    )
    unit: GraphEditUnit | None = Field(
        default=None,
        description="For add_unit: single graph unit (process, RLAgent, LLMAgent)",
    )
    pipeline: GraphEditPipeline | None = Field(
        default=None,
        description="For add_pipeline: RLGym or RLOracle pipeline (not a unit)",
    )
    code_block: GraphEditCodeBlock | None = Field(
        default=None, description="For add_code_block"
    )
    find_unit: FindUnit | None = Field(
        default=None, description="For replace_unit: unit to find"
    )
    replace_with: GraphEditUnit | None = Field(
        default=None, description="For replace_unit: new unit"
    )
    from_id: str | None = Field(
        default=None, alias="from", description="Source unit id for connect/disconnect"
    )
    to_id: str | None = Field(
        default=None, alias="to", description="Target unit id for connect/disconnect"
    )
    from_port: str | None = Field(
        default=None, description="Source output port index for connect (default '0')"
    )
    to_port: str | None = Field(
        default=None, description="Target input port index for connect (default '0')"
    )
    reason: str | None = Field(default=None, description="For no_edit")
    units: list[dict[str, JSONValue]] | None = Field(
        default=None, description="For replace_graph: full unit list"
    )
    connections: list[dict[str, str]] | None = Field(
        default=None, description="For replace_graph: full connection list"
    )
    # import_workflow: source = file path or URL
    source: str | None = Field(
        default=None, description="For import_workflow: file path or URL"
    )
    merge: bool = Field(
        default=False,
        description="For import_workflow: merge into current graph instead of replace",
    )
    # add_comment/remove_comment: agent note on the flow (stored in graph comments metadata; not exported to external runtimes)
    info: str | None = Field(default=None, description="For add_comment: comment text")
    commenter: str | None = Field(
        default=None,
        description="For add_comment: optional identifier of who left the comment (e.g. agent name)",
    )
    comment_id: str | None = Field(
            default=None,
            description="For remove_comment: id of the comment to remove",
        )
    # Todo list actions (graph metadata; not exported to runtimes)
    x: float | None = Field(default=None, description="X coordinate for todo list/task")
    y: float | None = Field(default=None, description="Y coordinate for todo list/task")
    title: str | None = Field(
        default=None, description="For add_todo_list: optional list title"
    )
    task_id: str | None = Field(
        default=None, description="For remove_task, mark_completed: task id"
    )
    text: str | None = Field(default=None, description="For add_task: task description")
    completed: bool = Field(
        default=True, description="For mark_completed: set completed (default true)"
    )
    # add_environment: add an environment to the graph so env-specific units become available in the Units Library
    env_id: str | None = Field(
        default=None,
        description="For add_environment: environment id (e.g. thermodynamic, data_bi)",
    )
    todo_list_id: str | None = Field(
        default=None,
        description="For add_task, remove_task, mark_completed: target todo list id (required when multiple todo lists exist).",
    )
    implementer: str | None = Field(
            default=None,
            description="For set_implementer: task implementer (optional; set null to clear).",
        )
    deadline: str | None = Field(
        default=None,
        description="For set_deadline: task deadline (optional; set null to clear).",
    )
    curator: str | None = Field(
        default=None,
        description="For set_curator: task curator (optional; set null to clear).",
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(
            populate_by_name=True,
        )


def _normalize_edit(edit: dict[str, JSONValue]) -> dict[str, JSONValue]:
    """If edit has units and connections but no action, treat it as replace_graph."""
    if edit.get("action") is not None:
        return dict(edit)

    if (
        isinstance(edit.get("units"), list)
        and isinstance(edit.get("connections"), list)
    ):
        return {**edit, "action": "replace_graph"}

    return dict(edit)


def _language_for_origin(origin: dict[str, JSONValue] | None) -> str | None:
    """Return expected code language from origin (runtime); uses centralized runtime_detector."""
    if not origin:
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
# LLM pipeline: Obs. sources -> Merge -> Prompt -> LLMAgent -> Switch -> action targets
_CANONICAL_MERGE_LLM_ID = "merge_llm"
_CANONICAL_PROMPT_LLM_ID = "prompt_llm"
_CANONICAL_PARSER_LLM_ID = "parser"

# Start port index for simulator units (Split output -> unit start input)
_START_PORT_BY_TYPE: dict[str, str] = {"Source": "0", "Tank": "5"}


def _ensure_canonical_topology(
    units: list[dict[str, JSONValue]],
    connections: list[dict[str, JSONValue]],
    obs_ids: list[str],
    act_ids: list[str],
    *,
    include_training_units: bool = True,
    include_http_endpoints: bool = False,
) -> None:
    """Ensure canonical units exist and are wired.
    - include_training_units=True (e.g. RLGym): Join, Switch, StepDriver, Split, StepRewards (full training).
    - include_training_units=False (e.g. RLAgent or add_unit LLMAgent): Join, Switch only (short: obs -> Join -> Agent -> Switch -> actions).
    - LLMSet pipeline uses _ensure_llm_canonical_topology: Obs (injects) -> Merge -> Prompt -> LLMAgent -> ProcessAgent -> action targets.
    - include_http_endpoints: add http_in, step_router, http_response only when True (external access)."""
    # Env-agnostic units (canonical + RLAgent/LLMAgent/RLGym/RLOracle) so they exist when adding from GUI or any env
    try:
        from units.register_env_agnostic import register_env_agnostic_units

        register_env_agnostic_units()
    except (ImportError, AttributeError):
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

    unit_ids: set[str] = {
        str(x["id"])
        for x in units
        if x.get("id") is not None
    }
    unit_by_id: dict[str, dict[str, JSONValue]] = {
        str(x["id"]): x
        for x in units
        if x.get("id") is not None
    }

    # Join: obs sources -> collector in_0, in_1, ...
    if _CANONICAL_JOIN_ID not in unit_ids:
        units.append(
            {
                "id": _CANONICAL_JOIN_ID,
                "type": type_join,
                "controllable": False,
                "params": {"num_inputs": max(len(obs_ids), 1)},
            }
        )
        unit_ids.add(_CANONICAL_JOIN_ID)
        for i, sid in enumerate(sorted(obs_ids)):
            if sid in unit_ids:
                connections.append(
                    {
                        "from": sid,
                        "to": _CANONICAL_JOIN_ID,
                        "from_port": "0",
                        "to_port": str(i),
                    }
                )

    # Switch: switch out_0, out_1, ... -> action targets (first input port)
    if _CANONICAL_SWITCH_ID not in unit_ids:
        units.append(
            {
                "id": _CANONICAL_SWITCH_ID,
                "type": type_switch,
                "controllable": False,
                "params": {"num_outputs": max(len(act_ids), 1)},
            }
        )
        unit_ids.add(_CANONICAL_SWITCH_ID)
        for i, tid in enumerate(sorted(act_ids)):
            if tid in unit_ids:
                connections.append(
                    {
                        "from": _CANONICAL_SWITCH_ID,
                        "to": tid,
                        "from_port": str(i),
                        "to_port": "0",
                    }
                )

    # Full training topology (RLGym): StepDriver, Split, StepRewards. Omit for short topology (RLAgent/LLMAgent only).
    if include_training_units:
        # StepDriver
        if _CANONICAL_STEP_DRIVER_ID not in unit_ids:
            units.append(
                {
                    "id": _CANONICAL_STEP_DRIVER_ID,
                    "type": type_step_driver,
                    "controllable": False,
                    "params": {},
                }
            )
            unit_ids.add(_CANONICAL_STEP_DRIVER_ID)

        # Split: step_driver out 0 -> split in 0; split out_i -> simulator i (start port). Always add Split when training units are included so topology is complete (wire to simulators when present).
        simulator_ids = [
            uid
            for uid in unit_ids
            if (unit_by_id.get(uid) or {}).get("type") in ("Source", "Tank")
        ]
        if _CANONICAL_SPLIT_ID not in unit_ids and type_split:
            units.append(
                {
                    "id": _CANONICAL_SPLIT_ID,
                    "type": type_split,
                    "controllable": False,
                    "params": {"num_outputs": max(len(simulator_ids), 1)},
                }
            )
            unit_ids.add(_CANONICAL_SPLIT_ID)
            connections.append(
                {
                    "from": _CANONICAL_STEP_DRIVER_ID,
                    "to": _CANONICAL_SPLIT_ID,
                    "from_port": "0",
                    "to_port": "0",
                }
            )
            for i, sim_id in enumerate(sorted(simulator_ids)):
                unit = unit_by_id.get(sim_id)
                unit_type = unit.get("type") if unit is not None else None

                to_port = _START_PORT_BY_TYPE.get(
                    unit_type if isinstance(unit_type, str) else "",
                    "0",
                )

                connections.append(
                    {
                        "from": _CANONICAL_SPLIT_ID,
                        "to": sim_id,
                        "from_port": str(i),
                        "to_port": to_port,
                    }
                )

        # StepRewards: Join → observation; StepDriver → trigger (executor also injects trigger when no connection).
        if type_step_rewards and _CANONICAL_JOIN_ID in unit_ids:
            if _CANONICAL_STEP_REWARDS_ID not in unit_ids:
                units.append(
                    {
                        "id": _CANONICAL_STEP_REWARDS_ID,
                        "type": type_step_rewards,
                        "controllable": False,
                        "params": {"max_steps": 600},
                    }
                )
                unit_ids.add(_CANONICAL_STEP_REWARDS_ID)
            connections.append(
                {
                    "from": _CANONICAL_JOIN_ID,
                    "to": _CANONICAL_STEP_REWARDS_ID,
                    "from_port": "observation",
                    "to_port": "observation",
                }
            )
            if _CANONICAL_STEP_DRIVER_ID in unit_ids:
                connections.append(
                    {
                        "from": _CANONICAL_STEP_DRIVER_ID,
                        "to": _CANONICAL_STEP_REWARDS_ID,
                        "from_port": "2",
                        "to_port": "1",
                    }
                )

    # HTTP endpoints (opt-in only): user adds when they want external access. Not part of standard wiring.
    if include_http_endpoints and type_http_in and type_http_response:
        if _CANONICAL_HTTP_IN_ID not in unit_ids:
            units.append(
                {
                    "id": _CANONICAL_HTTP_IN_ID,
                    "type": type_http_in,
                    "controllable": False,
                    "params": {},
                }
            )
            unit_ids.add(_CANONICAL_HTTP_IN_ID)
        if _CANONICAL_STEP_ROUTER_ID not in unit_ids:
            units.append(
                {
                    "id": _CANONICAL_STEP_ROUTER_ID,
                    "type": type_switch,
                    "controllable": False,
                    "params": {"num_outputs": 2},
                }
            )
            unit_ids.add(_CANONICAL_STEP_ROUTER_ID)
        if _CANONICAL_HTTP_RESPONSE_ID not in unit_ids:
            units.append(
                {
                    "id": _CANONICAL_HTTP_RESPONSE_ID,
                    "type": type_http_response,
                    "controllable": False,
                    "params": {},
                }
            )
            unit_ids.add(_CANONICAL_HTTP_RESPONSE_ID)
        # http_in output 0 → step_router (front switch) input 0
        connections.append(
            {
                "from": _CANONICAL_HTTP_IN_ID,
                "to": _CANONICAL_STEP_ROUTER_ID,
                "from_port": "0",
                "to_port": "0",
            }
        )
        # step_router output 0 → step_driver input 0; output 1 → switch (action demux) input 0
        connections.append(
            {
                "from": _CANONICAL_STEP_ROUTER_ID,
                "to": _CANONICAL_STEP_DRIVER_ID,
                "from_port": "0",
                "to_port": "0",
            }
        )
        connections.append(
            {
                "from": _CANONICAL_STEP_ROUTER_ID,
                "to": _CANONICAL_SWITCH_ID,
                "from_port": "1",
                "to_port": "0",
            }
        )
        # step response: StepRewards.payload → http_response (when present); else step_driver output 1 → http_response
        if _CANONICAL_STEP_REWARDS_ID in unit_ids:
            connections.append(
                {
                    "from": _CANONICAL_STEP_REWARDS_ID,
                    "to": _CANONICAL_HTTP_RESPONSE_ID,
                    "from_port": "payload",
                    "to_port": "payload",
                }
            )
        else:
            connections.append(
                {
                    "from": _CANONICAL_STEP_DRIVER_ID,
                    "to": _CANONICAL_HTTP_RESPONSE_ID,
                    "from_port": "1",
                    "to_port": "0",
                }
            )


def _default_workflow_designer_prompt_path() -> str:
    """Return Workflow Designer prompt path from app settings when available, else default."""
    try:
        from gui.components.settings import get_workflow_designer_prompt_path

        return str(get_workflow_designer_prompt_path())
    except (ImportError, AttributeError):
        return "config/prompts/workflow_designer.json"


def _ensure_llm_canonical_topology(
    units: list[dict[str, JSONValue]],
    connections: list[dict[str, JSONValue]],
    obs_ids: list[str],
    act_ids: list[str],
    llm_agent_id: str,
    *,
    prompt_template_path: str | None = None,
) -> None:
    """Ensure LLM pipeline topology: Merge, Prompt, ProcessAgent. Obs. sources (injects) -> Merge -> Prompt -> LLMAgent -> ProcessAgent -> action targets. No Switch; no apply_edits/graph_diff (agent-specific)."""
    if prompt_template_path is None:
        prompt_template_path = _default_workflow_designer_prompt_path()
    try:
        from units.register_env_agnostic import register_env_agnostic_units

        register_env_agnostic_units()
    except (ImportError, AttributeError):
        return

    unit_ids: set[str] = {
        str(x["id"])
        for x in units
        if x.get("id") is not None
    }
    n_obs = max(len(obs_ids), 1)
    n_obs = min(n_obs, 8)
    # Aggregate: observation sources (injects) -> in_0..in_{n-1}
    if _CANONICAL_MERGE_LLM_ID not in unit_ids:
        keys: list[JSONValue] = (
            list(obs_ids[:n_obs])
            if len(obs_ids) >= n_obs
            else [f"in_{i}" for i in range(n_obs)]
        )

        units.append(
            {
                "id": _CANONICAL_MERGE_LLM_ID,
                "type": "Aggregate",
                "controllable": False,
                "params": {
                    "num_inputs": n_obs,
                    "keys": keys,
                },
            }
        )
        unit_ids.add(_CANONICAL_MERGE_LLM_ID)
        for i, sid in enumerate(sorted(obs_ids)[:n_obs]):
            if sid in unit_ids:
                connections.append(
                    {
                        "from": sid,
                        "to": _CANONICAL_MERGE_LLM_ID,
                        "from_port": "0",
                        "to_port": str(i),
                    }
                )
    # Prompt: data from Merge -> system_prompt
    if _CANONICAL_PROMPT_LLM_ID not in unit_ids:
        units.append(
            {
                "id": _CANONICAL_PROMPT_LLM_ID,
                "type": "Prompt",
                "controllable": False,
                "params": {"template_path": prompt_template_path},
            }
        )
        unit_ids.add(_CANONICAL_PROMPT_LLM_ID)
        connections.append(
            {
                "from": _CANONICAL_MERGE_LLM_ID,
                "to": _CANONICAL_PROMPT_LLM_ID,
                "from_port": "data",
                "to_port": "data",
            }
        )
    # Prompt -> LLMAgent (system_prompt)
    if llm_agent_id in unit_ids:
        connections.append(
            {
                "from": _CANONICAL_PROMPT_LLM_ID,
                "to": llm_agent_id,
                "from_port": "system_prompt",
                "to_port": "system_prompt",
            }
        )
    # ProcessAgent: LLMAgent (action) -> parser (edits) -> action targets
    if _CANONICAL_PARSER_LLM_ID not in unit_ids:
        units.append(
            {
                "id": _CANONICAL_PARSER_LLM_ID,
                "type": "ProcessAgent",
                "controllable": False,
                "params": {},
            }
        )
        unit_ids.add(_CANONICAL_PARSER_LLM_ID)
    if llm_agent_id in unit_ids:
        connections.append(
            {
                "from": llm_agent_id,
                "to": _CANONICAL_PARSER_LLM_ID,
                "from_port": "action",
                "to_port": "action",
            }
        )
    for tid in sorted(act_ids):
        if tid in unit_ids:
            connections.append(
                {
                    "from": _CANONICAL_PARSER_LLM_ID,
                    "to": tid,
                    "from_port": "edits",
                    "to_port": "0",
                }
            )


def _ensure_unit_ports_from_registry(unit: dict[str, JSONValue]) -> None:
    """Set unit's input_ports and output_ports from registry (Registry → Graph). Mutates unit in place."""
    if unit.get("id") is None:
        return
    spec = get_unit_spec(str(unit.get("type", "")))
    if spec is not None:
        unit["input_ports"] = [
            {"name": n, "type": t or None} for n, t in spec.input_ports
        ]
        unit["output_ports"] = [
            {"name": n, "type": t or None} for n, t in spec.output_ports
        ]
    elif unit.get("input_ports") is None or unit.get("output_ports") is None:
        _ = unit.setdefault("input_ports", [])
        _ = unit.setdefault("output_ports", [])


def _validate_connect_disconnect(parsed: GraphEdit) -> None:
    """Raise if connect/disconnect is missing required from/to parameters."""
    if parsed.action == "connect":
        if parsed.from_id is None or parsed.to_id is None:
            missing = [
                k
                for k, v in [("from", parsed.from_id), ("to", parsed.to_id)]
                if v is None
            ]
            raise ValueError(
                f"Incorrect format for connect: missing required parameter(s): {', '.join(missing)}"
            )
    elif parsed.action == "disconnect" and (
        parsed.from_id is None or parsed.to_id is None
    ):
        missing = [
            k
            for k, v in [("from", parsed.from_id), ("to", parsed.to_id)]
            if v is None
        ]
        raise ValueError(
            f"Incorrect format for disconnect: missing required parameter(s): {', '.join(missing)}"
        )

def _duplicate_connection_exists(
    connections: list[dict[str, JSONValue]],
    *,
    from_id: str,
    to_id: str,
    from_port: str,
    to_port: str,
) -> bool:
    """Return whether an edge with the same source, target, and ports exists."""
    for connection in connections:
        if (
            connection.get("from") != from_id
            or connection.get("to") != to_id
        ):
            continue

        if (
            str(connection.get("from_port", "0")) == from_port
            and str(connection.get("to_port", "0")) == to_port
        ):
            return True

    return False


def _assert_no_duplicate_connections(
    connections: list[dict[str, JSONValue]],
) -> None:
    """Raise if any two connections share the same endpoints and ports."""
    seen: set[tuple[str, str, str, str]] = set()

    for connection in connections:
        from_id = str(connection.get("from", ""))
        to_id = str(connection.get("to", ""))
        from_port = str(connection.get("from_port", "0"))
        to_port = str(connection.get("to_port", "0"))

        key = (from_id, to_id, from_port, to_port)

        if key in seen:
            raise ValueError(
                "Duplicate connection: "
                + f"from={from_id!r}, "
                + f"to={to_id!r}, "
                + f"from_port={from_port!r}, "
                + f"to_port={to_port!r}"
            )

        seen.add(key)

def get_string_list(
    params: dict[str, JSONValue],
    key: str,
    fallback: set[str],
) -> list[str]:
    value = params.get(key)

    if not isinstance(value, list):
        return sorted(fallback)

    string_values = [
        item
        for item in value
        if isinstance(item, str)
    ]

    if len(string_values) != len(value):
        return sorted(fallback)  # or raise ValueError(...)

    return string_values or sorted(fallback)

def _json_string_list(values: set[str]) -> list[JSONValue]:
    return [value for value in sorted(values)]

def apply_graph_edit(current: dict[str, JSONValue], edit: dict[str, JSONValue]) -> dict[str, JSONValue]:
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
    if parsed.action == "import_workflow":
        raise ValueError(
            "import_workflow must be resolved via apply_workflow_edits (batch_edits)"
        )

    if parsed.action == "add_environment":
        raw_env_id = parsed.env_id

        if not isinstance(raw_env_id, str):
            raw_id = edit.get("id")
            raw_env_id = raw_id if isinstance(raw_id, str) else ""

        env_id_raw = raw_env_id.strip().lower()

        if not env_id_raw:
            raise ValueError(
                "add_environment requires env_id (e.g. thermodynamic, data_bi)"
            )

        from units.env_loaders import known_environment_tags

        known = known_environment_tags()
        if env_id_raw not in known:
            raise ValueError(
                f"Unknown environment: {env_id_raw!r}. Known: {sorted(known)}"
            )

        raw_environments = current.get("environments")

        if isinstance(raw_environments, list):
            environments = {
                item for item in raw_environments
                if isinstance(item, str)
            }
        else:
            environments = set[str]()

        result = dict(current)
        result["environments"] = _json_string_list(
            environments | {env_id_raw}
        )

        return result

    add_code_block_payload: dict[str, JSONValue] | None = None
    add_oracle_code_blocks: list[dict[str, JSONValue]] = []
    add_pyflow_code_blocks: list[dict[str, JSONValue]] = []
    add_node_red_code_blocks: list[dict[str, JSONValue]] = []
    add_n8n_code_blocks: list[dict[str, JSONValue]] = []

    raw_comments = current.get("comments")
    if isinstance(raw_comments, list):
        comments: list[dict[str, JSONValue]] = [
            item for item in raw_comments
            if isinstance(item, dict)
        ]
    else:
        comments = []

    raw_todo_lists = current.get("todo_lists")

    if isinstance(raw_todo_lists, list):
        todo_lists = todo_lists_to_list(
            cast(list[JSONValue | TodoList], raw_todo_lists)
        )
    else:
        todo_lists = todo_lists_to_list(None)
    env_type = current.get("environment_type", "data_bi")

    raw_units = current.get("units")
    if isinstance(raw_units, list):
        units: list[dict[str, JSONValue]] = [
            unit.copy()
            for unit in raw_units
            if isinstance(unit, dict)
        ]
    else:
        units = []

    connections: list[dict[str, JSONValue]] = []

    raw_connections = current.get("connections")
    if isinstance(raw_connections, list):
        for connection in raw_connections:
            if not isinstance(connection, dict):
                continue

            raw_from_id = connection.get("from")
            if raw_from_id is None:
                raw_from_id = connection.get("from_id")

            raw_to_id = connection.get("to")
            if raw_to_id is None:
                raw_to_id = connection.get("to_id")

            if raw_from_id is None or raw_to_id is None:
                continue

            from_id = str(raw_from_id)
            to_id = str(raw_to_id)

            edge: dict[str, JSONValue] = {
                "from": from_id,
                "to": to_id,
                "from_port": str(connection.get("from_port", "0")),
                "to_port": str(connection.get("to_port", "0")),
            }

            connection_type = connection.get("connection_type")
            if connection_type is not None:
                edge["connection_type"] = str(connection_type)

            connections.append(edge)


    # Validate and normalize: pipeline types (LLMSet, RLSet, RLGym, RLOracle) must use add_pipeline;
    # graph unit types (RLAgent, LLMAgent) must use add_unit. Normalize add_unit with pipeline type → add_pipeline.
    if parsed.action == "add_pipeline" and parsed.pipeline is not None:
        p = parsed.pipeline
    elif (
        parsed.action == "add_unit"
        and parsed.unit is not None
        and parsed.unit.type in PIPELINE_TYPES
    ):
        u = parsed.unit
        p = GraphEditPipeline(
            id=u.id,
            type=u.type,
            params=dict(u.params) if u.params else {},
        )
    else:
        # If it's add_unit but unit.type not in PIPELINE_TYPES → handled by next block (add_unit)
        # So skip pipeline logic here
        p = None

    # Only proceed if p is a pipeline (i.e., not None)
    if p is not None:
        # Validate pipeline type: RL/LLM agents must NOT be added as pipelines
        if p.type in RL_AGENT_NODE_TYPES or p.type in LLM_AGENT_NODE_TYPES:
            from agents.prompts import (
                WORKFLOW_DESIGNER_ADD_PIPELINE_USE_ADD_UNIT_ERROR,
            )

            raise ValueError(
                WORKFLOW_DESIGNER_ADD_PIPELINE_USE_ADD_UNIT_ERROR.format(
                    unit_type=p.type
                )
            )

        if p.type not in PIPELINE_TYPES:
            from agents.prompts import (
                WORKFLOW_DESIGNER_ADD_PIPELINE_REQUIRED_TYPES_ERROR,
            )

            raise ValueError(
                WORKFLOW_DESIGNER_ADD_PIPELINE_REQUIRED_TYPES_ERROR.format(
                    unit_type=p.type
                )
            )
        if any(x["id"] == p.id for x in units):
            raise ValueError(f"Unit id already exists: {p.id}")
        if p.type == RL_GYM_NODE_TYPE:
            # Full training setup for our runtime: Join, StepRewards, Switch, StepDriver, Split.
            if get_unit_spec(RL_GYM_NODE_TYPE) is None:
                try:
                    from units.pipelines.rl_gym import register_rl_gym

                    register_rl_gym()
                except (ImportError, AttributeError):
                    pass
            raw_obs_ids = p.params.get("observation_source_ids")
            raw_act_ids = p.params.get("action_target_ids")

            if isinstance(raw_obs_ids, list):
                obs_ids: list[str] = [str(value) for value in raw_obs_ids]
            else:
                obs_ids = []

            if isinstance(raw_act_ids, list):
                act_ids: list[str] = [str(value) for value in raw_act_ids]
            else:
                act_ids = []

            _ensure_canonical_topology(
                units, connections, obs_ids, act_ids, include_training_units=True
            )
            units.append(
                {
                    "id": p.id,
                    "type": RL_GYM_NODE_TYPE,
                    "controllable": False,
                    "params": {k: v for k, v in (p.params or {}).items()},
                }
            )
        elif p.type == "RLOracle":
            raw_adapter_config = p.params.get("adapter_config")

            if isinstance(raw_adapter_config, dict):
                adapter_config: dict[str, JSONValue] = raw_adapter_config.copy()
            else:
                adapter_config = p.params.copy()

            raw_origin = current.get("origin")
            oracle_origin: dict[str, JSONValue] = (
                raw_origin if isinstance(raw_origin, dict) else {}
            )

            lang = _language_for_origin(oracle_origin) or "python"

            raw_oracle_obs_ids = p.params.get("observation_source_ids")
            if raw_oracle_obs_ids is None:
                raw_oracle_obs_ids = adapter_config.get("observation_sources")
            if raw_oracle_obs_ids is None:
                raw_oracle_obs_ids = adapter_config.get(
                    "observation_source_ids"
                )

            oracle_obs_ids: list[str] = []
            if isinstance(raw_oracle_obs_ids, list):
                oracle_obs_ids.extend(
                    str(value) for value in raw_oracle_obs_ids
                )

            raw_oracle_act_ids = p.params.get("action_target_ids")
            if raw_oracle_act_ids is None:
                raw_oracle_act_ids = adapter_config.get(
                    "action_target_ids"
                )
            if raw_oracle_act_ids is None:
                raw_oracle_act_ids = adapter_config.get(
                    "action_targets"
                )

            oracle_act_ids: list[str] = []
            if isinstance(raw_oracle_act_ids, list):
                oracle_act_ids.extend(
                    str(value) for value in raw_oracle_act_ids
                )

            json_observation_source_ids: list[JSONValue] = [
                value for value in oracle_obs_ids
            ]

            json_action_target_ids: list[JSONValue] = [
                value for value in oracle_act_ids
            ]

            adapter_config["observation_source_ids"] = (
                json_observation_source_ids
            )
            adapter_config["action_target_ids"] = (
                json_action_target_ids
            )

            _ensure_canonical_topology(
                units,
                connections,
                oracle_obs_ids,
                oracle_act_ids,
                include_http_endpoints=True,
            )

            cbs = render_oracle_code_blocks_for_canonical(
                adapter_config,
                language=lang,
                observation_source_ids=oracle_obs_ids or None,
                n8n_mode=(runtime_label(current) == "n8n"),
            )

            add_oracle_code_blocks.extend(cbs)

        elif p.type == "RLSet":
            # Full RL agent set: Join, Switch, RLAgent unit, wiring,
            # and code blocks. Same params as the RLAgent unit.

            raw_rlset_obs_ids = p.params.get("observation_source_ids")
            raw_rlset_act_ids = p.params.get("action_target_ids")

            rlset_obs_ids: list[str] = []
            if isinstance(raw_rlset_obs_ids, list):
                rlset_obs_ids.extend(
                    str(value) for value in raw_rlset_obs_ids
                )

            rlset_act_ids: list[str] = []
            if isinstance(raw_rlset_act_ids, list):
                rlset_act_ids.extend(
                    str(value) for value in raw_rlset_act_ids
                )

            _ensure_canonical_topology(
                units,
                connections,
                rlset_obs_ids,
                rlset_act_ids,
                include_training_units=False,
            )

            raw_rl_model_path = p.params.get("model_path")
            rl_model_path: JSONValue = (
                raw_rl_model_path
                if raw_rl_model_path is not None
                else ""
            )

            raw_rl_inference_url = p.params.get("inference_url")
            rl_inference_url = (
                str(raw_rl_inference_url)
                if raw_rl_inference_url
                else "http://127.0.0.1:8000/predict"
            )

            units.append(
                {
                    "id": p.id,
                    "type": "RLAgent",
                    "controllable": False,
                    "params": {
                        "model_path": rl_model_path,
                        **{
                            key: value
                            for key, value in p.params.items()
                            if key not in (
                                "observation_source_ids",
                                "action_target_ids",
                            )
                        },
                    },
                }
            )

            connections.append(
                {
                    "from": _CANONICAL_JOIN_ID,
                    "to": p.id,
                    "from_port": "0",
                    "to_port": "0",
                }
            )

            connections.append(
                {
                    "from": p.id,
                    "to": _CANONICAL_SWITCH_ID,
                    "from_port": "0",
                    "to_port": "0",
                }
            )

            raw_rlset_origin = current.get("origin")
            rlset_origin: dict[str, JSONValue] = (
                raw_rlset_origin
                if isinstance(raw_rlset_origin, dict)
                else {}
            )

            lang = _language_for_origin(rlset_origin) or "python"

            if lang == "python":
                code_src = render_rl_agent_predict_py(
                    rl_inference_url,
                    rlset_obs_ids,
                )

                add_oracle_code_blocks.append(
                    {
                        "id": p.id,
                        "language": "python",
                        "source": code_src,
                    }
                )

            elif runtime_label(current) == "n8n":
                code_src = render_rl_agent_predict_n8n(
                    rl_inference_url,
                    rlset_obs_ids,
                )

                add_oracle_code_blocks.append(
                    {
                        "id": p.id,
                        "language": "javascript",
                        "source": code_src,
                    }
                )

            else:
                code_src = render_rl_agent_predict_js(
                    rl_inference_url,
                    rlset_obs_ids,
                )

                add_oracle_code_blocks.append(
                    {
                        "id": p.id,
                        "language": "javascript",
                        "source": code_src,
                    }
                )

        elif p.type == "LLMSet":
            raw_llm_obs_ids = p.params.get("observation_source_ids")
            raw_llm_act_ids = p.params.get("action_target_ids")

            llm_obs_ids: list[str] = []
            if isinstance(raw_llm_obs_ids, list):
                llm_obs_ids.extend(str(value) for value in raw_llm_obs_ids)

            llm_act_ids: list[str] = []
            if isinstance(raw_llm_act_ids, list):
                llm_act_ids.extend(str(value) for value in raw_llm_act_ids)

            repo_root = Path(__file__).resolve().parent.parent.parent
            template = load_pipeline_template("LLMSet", base_path=repo_root)

            if template is not None:
                existing_ids: set[str] = {
                    str(unit.get("id", ""))
                    for unit in units
                    if unit.get("id") is not None
                }

                merge_pipeline_into_graph(
                    units,
                    connections,
                    template,
                    p.id,
                    p.params.copy(),
                    llm_obs_ids,
                    llm_act_ids,
                    existing_ids,
                )

            else:
                llm_params = {
                    key: value
                    for key, value in p.params.items()
                    if key not in (
                        "observation_source_ids",
                        "action_target_ids",
                    )
                }

                units.append(
                    {
                        "id": p.id,
                        "type": "LLMAgent",
                        "controllable": False,
                        "params": llm_params,
                    }
                )

                raw_template_path = p.params.get("template_path")
                if not isinstance(raw_template_path, str) or not raw_template_path:
                    raw_template_path = p.params.get("prompt_template_path")

                prompt_template_path = (
                    raw_template_path
                    if isinstance(raw_template_path, str) and raw_template_path
                    else str(_default_workflow_designer_prompt_path())
                )

                _ensure_llm_canonical_topology(
                    units,
                    connections,
                    llm_obs_ids,
                    llm_act_ids,
                    p.id,
                    prompt_template_path=prompt_template_path,
                )

            raw_inference_url = p.params.get("inference_url")
            inference_url = (
                str(raw_inference_url)
                if raw_inference_url
                else "http://127.0.0.1:8001/predict"
            )

            raw_system_prompt = p.params.get("system_prompt")
            system_prompt = (
                str(raw_system_prompt)
                if raw_system_prompt
                else (
                    "You are a control agent. Given observations, output a JSON "
                    "object with an 'action' key containing a list of numbers."
                )
            )

            raw_user_prompt_template = p.params.get("user_prompt_template")
            user_prompt_template = (
                str(raw_user_prompt_template)
                if raw_user_prompt_template
                else (
                    "Observations: {observation_json}. Output only a JSON object "
                    "with key 'action' and value a list of numbers."
                )
            )

            raw_model_name = p.params.get("model_name")
            model_name = str(raw_model_name) if raw_model_name else "llama3.2"

            raw_provider = p.params.get("provider")
            provider = str(raw_provider) if raw_provider else "ollama"

            raw_host = p.params.get("host")
            host = str(raw_host) if raw_host else ""

            raw_llm_origin = current.get("origin")
            llm_origin: dict[str, JSONValue] = (
                raw_llm_origin if isinstance(raw_llm_origin, dict) else {}
            )

            lang = _language_for_origin(llm_origin) or "python"

            if lang == "python":
                code_src = render_llm_agent_predict_py(
                    inference_url,
                    llm_obs_ids,
                    system_prompt,
                    user_prompt_template,
                    model_name,
                    provider,
                    host,
                )

                add_oracle_code_blocks.append(
                    {
                        "id": p.id,
                        "language": "python",
                        "source": code_src,
                    }
                )

            elif runtime_label(current) == "n8n":
                code_src = render_llm_agent_predict_n8n(
                    inference_url,
                    llm_obs_ids,
                    system_prompt,
                    user_prompt_template,
                    model_name,
                    provider,
                    host,
                )

                add_oracle_code_blocks.append(
                    {
                        "id": p.id,
                        "language": "javascript",
                        "source": code_src,
                    }
                )

            else:
                code_src = render_llm_agent_predict_js(
                    inference_url,
                    llm_obs_ids,
                    system_prompt,
                    user_prompt_template,
                    model_name,
                    provider,
                    host,
                )

                add_oracle_code_blocks.append(
                    {
                        "id": p.id,
                        "language": "javascript",
                        "source": code_src,
                    }
                )

        # System comment with wiring guidelines when any canonical pipeline is added
        comment_id = "comment_" + uuid4().hex[:8]
        created_at = datetime.datetime.now(datetime.UTC).strftime(
            "%y-%m-%d-%H%M%S"
        )

        comments.append(
            {
                "id": comment_id,
                "info": _pipeline_wiring_guideline_message(p.type),
                "commenter": "system",
                "created_at": created_at,
            }
        )

    elif parsed.action == "add_unit" and parsed.unit is not None:
        u = parsed.unit

        if any(
            existing_unit.get("id") == u.id
            for existing_unit in units
        ):
            raise ValueError(f"Unit id already exists: {u.id}")

        # Type must be in the Units Library unless coding is allowed.
        if get_unit_spec(u.type) is None and not _coding_is_allowed():
            raise ValueError("Invalid unit. Use units from the Units Library.")

        _reject_custom_code_unit_if_disabled(u.type)

        if u.type in RL_AGENT_NODE_TYPES:
            raw_model_path = u.params.get("model_path")
            model_path: JSONValue = (
                raw_model_path if raw_model_path is not None else ""
            )

            source_ids: set[str] = set()
            target_ids: set[str] = set()

            for connection in connections:
                raw_from_id = connection.get("from")
                if raw_from_id is None:
                    raw_from_id = connection.get("from_id")

                raw_to_id = connection.get("to")
                if raw_to_id is None:
                    raw_to_id = connection.get("to_id")

                if raw_from_id is None or raw_to_id is None:
                    continue

                from_id = str(raw_from_id)
                to_id = str(raw_to_id)

                if to_id == u.id:
                    source_ids.add(from_id)

                if from_id == u.id:
                    target_ids.add(to_id)

            raw_obs_ids = u.params.get("observation_source_ids")
            raw_act_ids = u.params.get("action_target_ids")

            rl_obs_ids: list[str] = []
            if isinstance(raw_obs_ids, list):
                rl_obs_ids.extend(str(value) for value in raw_obs_ids)
            else:
                rl_obs_ids.extend(sorted(source_ids))

            rl_act_ids: list[str] = []
            if isinstance(raw_act_ids, list):
                rl_act_ids.extend(str(value) for value in raw_act_ids)
            else:
                rl_act_ids.extend(sorted(target_ids))

            _ensure_canonical_topology(
                units,
                connections,
                rl_obs_ids,
                rl_act_ids,
                include_training_units=False,
            )

            raw_inference_url = u.params.get("inference_url")
            inference_url = (
                str(raw_inference_url)
                if raw_inference_url
                else "http://127.0.0.1:8000/predict"
            )

            units.append(
                {
                    "id": u.id,
                    "type": u.type,
                    "controllable": False,
                    "params": {
                        "model_path": model_path,
                        **{
                            key: value
                            for key, value in u.params.items()
                            if key not in (
                                "observation_source_ids",
                                "action_target_ids",
                            )
                        },
                    },
                }
            )

            connections.append(
                {
                    "from": _CANONICAL_JOIN_ID,
                    "to": u.id,
                    "from_port": "0",
                    "to_port": "0",
                }
            )

            connections.append(
                {
                    "from": u.id,
                    "to": _CANONICAL_SWITCH_ID,
                    "from_port": "0",
                    "to_port": "0",
                }
            )

            raw_origin = current.get("origin")
            rl_origin: dict[str, JSONValue] = (
                raw_origin if isinstance(raw_origin, dict) else {}
            )

            lang = _language_for_origin(rl_origin) or "python"

            if lang == "python":
                code_src = render_rl_agent_predict_py(
                    inference_url,
                    rl_obs_ids,
                )

                add_oracle_code_blocks.append(
                    {
                        "id": u.id,
                        "language": "python",
                        "source": code_src,
                    }
                )

            elif runtime_label(current) == "n8n":
                code_src = render_rl_agent_predict_n8n(
                    inference_url,
                    rl_obs_ids,
                )

                add_oracle_code_blocks.append(
                    {
                        "id": u.id,
                        "language": "javascript",
                        "source": code_src,
                    }
                )

            else:
                code_src = render_rl_agent_predict_js(
                    inference_url,
                    rl_obs_ids,
                )

                add_oracle_code_blocks.append(
                    {
                        "id": u.id,
                        "language": "javascript",
                        "source": code_src,
                    }
                )

        elif u.type in LLM_AGENT_NODE_TYPES:
            unit_ids: set[str] = {
                str(unit_id)
                for x in units
                if isinstance(unit_id := x.get("id"), (str, int, float, bool))
            }

            source_ids = {
                str(c.get("from") or c.get("from_id", ""))
                for c in connections
                if (c.get("to") or c.get("to_id", "")) == u.id
                and (c.get("from") or c.get("from_id")) is not None
            }


            target_ids = {
                str(c.get("to") or c.get("to_id", ""))  # safe str()
                for c in connections
                if (c.get("from") or c.get("from_id", ""))
                == u.id  # connection starts at u.id
                and (c.get("to") or c.get("to_id"))
                is not None  # filters to only real targets
            }


            obs_ids = get_string_list(
                u.params,
                "observation_source_ids",
                source_ids,
            )

            act_ids = get_string_list(
                u.params,
                "action_target_ids",
                target_ids,
            )


            _ensure_canonical_topology(
                units,
                connections,
                obs_ids or [],
                act_ids or [],
                include_training_units=False,
            )
            inference_url = str(
                u.params.get("inference_url") or "http://127.0.0.1:8001/predict"
            )
            system_prompt = str(
                u.params.get("system_prompt")
                or "You are a control agent. Given observations, output a JSON object with an 'action' key containing a list of numbers."
            )
            user_prompt_template = str(
                u.params.get("user_prompt_template")
                or "Observations: {observation_json}. Output only a JSON object with key 'action' and value a list of numbers."
            )
            model_name = str(u.params.get("model_name") or "llama3.2")
            provider = str(u.params.get("provider") or "ollama")
            host = str(u.params.get("host") or "")
            llm_params = {
                k: v
                for k, v in u.params.items()
                if k not in ("observation_source_ids", "action_target_ids")
            }
            units.append(
                {
                    "id": u.id,
                    "type": u.type,
                    "controllable": False,
                    "params": llm_params,
                }
            )
            connections.append(
                {
                    "from": _CANONICAL_JOIN_ID,
                    "to": u.id,
                    "from_port": "0",
                    "to_port": "0",
                }
            )
            connections.append(
                {
                    "from": u.id,
                    "to": _CANONICAL_SWITCH_ID,
                    "from_port": "0",
                    "to_port": "0",
                }
            )
            raw_origin = current.get("origin")
            origin: dict[str, JSONValue] = (
                raw_origin if isinstance(raw_origin, dict) else {}
            )

            lang = _language_for_origin(origin) or "python"

            if lang == "python":
                code_src = render_llm_agent_predict_py(
                    inference_url,
                    obs_ids,
                    system_prompt,
                    user_prompt_template,
                    model_name,
                    provider,
                    host,
                )
                add_oracle_code_blocks.append(
                    {"id": u.id, "language": "python", "source": code_src}
                )
            elif runtime_label(current) == "n8n":
                code_src = render_llm_agent_predict_n8n(
                    inference_url,
                    obs_ids if obs_ids else [],
                    system_prompt,
                    user_prompt_template,
                    model_name,
                    provider,
                    host,
                )
                add_oracle_code_blocks.append(
                    {"id": u.id, "language": "javascript", "source": code_src}
                )
            else:
                code_src = render_llm_agent_predict_js(
                    inference_url,
                    obs_ids if obs_ids else [],
                    system_prompt,
                    user_prompt_template,
                    model_name,
                    provider,
                    host,
                )
                add_oracle_code_blocks.append(
                    {"id": u.id, "language": "javascript", "source": code_src}
                )
        else:
            add_u: dict[str, JsonValue] = {
                "id": u.id,
                "type": u.type,
                "controllable": u.controllable,
                "params": dict(u.params),
            }
            if u.name is not None and str(u.name).strip():
                add_u["name"] = str(u.name).strip()
            units.append(add_u)
            # PyFlow catalog: when agent adds a unit of a PyFlow type, attach template as code_block
            if u.type in get_pyflow_types():
                entry = get_pyflow_template(u.type)
                if entry and entry.get("code_template"):
                    add_pyflow_code_blocks.append(
                        {
                            "id": u.id,
                            "language": "python",
                            "source": entry["code_template"],
                        }
                    )
            # Node-RED catalog: when graph is node_red and unit type is in catalog, attach JS template for export
            if runtime_label(current) == "node_red" and u.type in get_node_red_types():
                entry = get_node_red_template(u.type)
                if entry and entry.get("code_template"):
                    add_node_red_code_blocks.append(
                        {
                            "id": u.id,
                            "language": "javascript",
                            "source": entry["code_template"],
                        }
                    )
            # n8n catalog: when graph is n8n and unit type is in catalog, attach JS template for export
            if runtime_label(current) == "n8n" and u.type in get_n8n_types():
                entry = get_n8n_template(u.type)
                if entry and entry.get("code_template"):
                    add_n8n_code_blocks.append(
                        {
                            "id": u.id,
                            "language": "javascript",
                            "source": entry["code_template"],
                        }
                    )

    elif parsed.action == "remove_unit":
        if parsed.unit_id is None:
            raise ValueError(
                "Incorrect format for remove_unit: missing required parameter: unit_id"
            )
        uid = parsed.unit_id
        to_remove: set[str] = {uid}
        if not any(x.get("id") == uid for x in units):
            raise ValueError(f"Unit id does not exist: {uid}")
        units = [x for x in units if x.get("id") not in to_remove]
        connections = [
            c
            for c in connections
            if c.get("from") not in to_remove and c.get("to") not in to_remove
        ]

    elif parsed.action == "set_params":
        # No unit-type check: allow params on any unit by id (including custom/function units when coding_is_allowed).
        uid = parsed.id
        if not uid:
            raise ValueError(
                "Incorrect format for set_params: missing required parameter: id"
            )
        if parsed.new_params is None:
            raise ValueError(
                "Incorrect format for set_params: missing or invalid new_params (must be a JSON object)"
            )
        unit_ids = {
            unit_id
            for unit in units
            if isinstance(unit_id := unit.get("id"), str)
        }
        if uid not in unit_ids:
            from agents.prompts import (
                WORKFLOW_DESIGNER_SET_PARAMS_UNIT_NOT_FOUND_ERROR,
            )

            raise ValueError(
                WORKFLOW_DESIGNER_SET_PARAMS_UNIT_NOT_FOUND_ERROR.format(unit_id=uid)
            )
        for u in units:
            if u.get("id") == uid:
                existing = u.get("params")
                if not isinstance(existing, dict):
                    existing = {}
                u["params"] = {**existing, **parsed.new_params}
                break

    elif parsed.action == "connect":
        _validate_connect_disconnect(parsed)

        from_id = str(parsed.from_id)
        to_id = str(parsed.to_id)

        unit_ids = {
            unit_id
            for unit in units
            if isinstance(unit_id := unit.get("id"), str)
        }
        if from_id not in unit_ids:
            raise ValueError(f"Unit id does not exist: {from_id}")
        if to_id not in unit_ids:
            raise ValueError(f"Unit id does not exist: {to_id}")
        from_port = str(parsed.from_port) if parsed.from_port is not None else "0"
        to_port = str(parsed.to_port) if parsed.to_port is not None else "0"
        if _duplicate_connection_exists(
            connections,
            from_id=from_id,
            to_id=to_id,
            from_port=from_port,
            to_port=to_port,
        ):
            raise ValueError(
                f"Duplicate connection: from={from_id!r}, to={to_id!r}, from_port={from_port!r}, to_port={to_port!r}"
            )
        connections.append(
            {"from": from_id, "to": to_id, "from_port": from_port, "to_port": to_port}
        )

    elif parsed.action == "disconnect":
        _validate_connect_disconnect(parsed)

        from_id = str(parsed.from_id)
        to_id = str(parsed.to_id)

        unit_ids = {
            unit_id
            for unit in units
            if isinstance(unit_id := unit.get("id"), str)
        }
        # Match by from/to (optionally from_port/to_port if specified)
        from_port = str(parsed.from_port) if parsed.from_port is not None else None
        to_port = str(parsed.to_port) if parsed.to_port is not None else None
        matching = [
            c
            for c in connections
            if c.get("from") == from_id
            and c.get("to") == to_id
            and (from_port is None or c.get("from_port", "0") == from_port)
            and (to_port is None or c.get("to_port", "0") == to_port)
        ]
        if not matching:
            raise ValueError(
                f"Connection does not exist: from={parsed.from_id}, to={parsed.to_id}"
                + (
                    f" (from_port={from_port}, to_port={to_port})"
                    if from_port or to_port
                    else ""
                )
            )
        connections = [
            c
            for c in connections
            if not (
                c.get("from") == from_id
                and c.get("to") == to_id
                and (from_port is None or c.get("from_port", "0") == from_port)
                and (to_port is None or c.get("to_port", "0") == to_port)
            )
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
        if get_unit_spec(new_unit.type) is None and not _coding_is_allowed():
            raise ValueError("Invalid unit. Use units from the Units Library.")
        _reject_custom_code_unit_if_disabled(new_unit.type)
        # Remove old unit
        units = [x for x in units if x.get("id") != old_id]
        # Add new unit
        new_u: dict[str, JsonValue] = {
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
        unit_ids = {
            unit_id
            for unit in units
            if isinstance(unit_id := unit.get("id"), str)
        }
        if cb.id not in unit_ids:
            raise ValueError(f"Unit id does not exist: {cb.id}")
        raw_origin = current.get("origin")

        if isinstance(raw_origin, dict):
            expected_lang = _language_for_origin(raw_origin)
        else:
            expected_lang = _language_for_origin(None)

        if expected_lang is not None and cb.language.lower() != expected_lang:
            raise ValueError(
                f"Language must match origin runtime: expected '{expected_lang}' (e.g. Node-RED→javascript, PyFlow→python), got '{cb.language}'"
            )
        # add_code_block mutates code_blocks below; we mark it here
        add_code_block_payload = {
            "id": cb.id,
            "language": cb.language,
            "source": cb.source,
        }

    elif parsed.action == "add_comment":
        if not parsed.info or not str(parsed.info).strip():
            raise ValueError(
                "Incorrect format for add_comment: missing required parameter: info (non-empty string)"
            )
        comment_id = "comment_" + uuid4().hex[:8]
        created_at = datetime.datetime.now(datetime.UTC).strftime("%y-%m-%d-%H%M%S")
        comments.append(
            {
                "id": comment_id,
                "info": str(parsed.info).strip(),
                "commenter": str(parsed.commenter).strip()
                if parsed.commenter and str(parsed.commenter).strip()
                else "",
                "created_at": created_at,
            }
        )

    elif parsed.action == "remove_comment":
        if not getattr(parsed, "comment_id", None) or not str(parsed.comment_id).strip():
            raise ValueError("Incorrect format for remove_comment: missing required parameter: comment_id")

        comment_id = str(parsed.comment_id).strip()

        before_len = len(comments)
        comments[:] = [c for c in comments if str(c.get("id", "")).strip() != comment_id]
        if len(comments) == before_len:
            raise ValueError(f"remove_comment: comment_id not found: {comment_id}")


    elif parsed.action == "add_todo_list":
        from core.graph.todo_list import create_new_todo_list as todo_create_new_list

        existing = normalize_todo_lists(todo_lists)
        existing_ids = {todo_list.id for todo_list in existing}

        if parsed.id and str(parsed.id).strip():
            list_id = str(parsed.id).strip()

            if list_id in existing_ids:
                raise ValueError(f"Todo list id already exists: {list_id}")
        else:
            i = 1
            while f"todo_list_default_{i}" in existing_ids:
                i += 1

            list_id = f"todo_list_default_{i}"

        todo_lists = todo_create_new_list(
            existing,
            title=parsed.title,
            list_id=list_id,
        )


    elif parsed.action == "remove_todo_list":
        if not parsed.id or not str(parsed.id).strip():
            raise ValueError(
                "Incorrect format for remove_todo_list: "
                + "missing required parameter: id"
            )

        target_id = str(parsed.id).strip()

        existing = normalize_todo_lists(todo_lists)

        filtered_lists = [
            todo_list
            for todo_list in existing
            if str(todo_list.id) != target_id
        ]

        if len(filtered_lists) == len(existing):
            raise ValueError(f"Todo list not found: {target_id}")

        todo_lists = filtered_lists


    elif parsed.action == "add_task":
        if not parsed.text or not str(parsed.text).strip():
            raise ValueError(
                "Incorrect format for add_task: "
                + "missing required parameter: text (non-empty string)"
            )

        from core.graph.todo_list import add_task as todo_add_task

        existing = normalize_todo_lists(todo_lists)

        if not existing:
            raise ValueError("No todo lists exist")

        if len(existing) == 1:
            target_list_id = str(existing[0].id)
        else:
            if not parsed.todo_list_id or not str(parsed.todo_list_id).strip():
                raise ValueError(
                    "Incorrect format for add_task: "
                    + "missing required parameter: todo_list_id (todo list id)"
                )

            target_list_id = str(parsed.todo_list_id).strip()

        task_text = str(parsed.text).strip()
        task_added = False
        new_lists_for_add: list[TodoList] = []

        for todo_list in existing:
            if str(todo_list.id) == target_list_id:
                new_lists_for_add.append(
                    todo_add_task(todo_list, task_text)
                )
                task_added = True
            else:
                new_lists_for_add.append(todo_list)

        if not task_added:
            raise ValueError(f"Todo list not found: {target_list_id}")

        todo_lists = new_lists_for_add


    elif parsed.action == "remove_task":
        if not parsed.task_id or not str(parsed.task_id).strip():
            raise ValueError(
                "Incorrect format for remove_task: "
                + "missing required parameter: task_id"
            )

        from core.graph.todo_list import (
            remove_task as todo_remove_task,
        )

        task_id = str(parsed.task_id).strip()
        existing = normalize_todo_lists(todo_lists)

        if not existing:
            raise ValueError("No todo lists exist")

        if len(existing) == 1:
            target_list_id = str(existing[0].id)
        else:
            if not parsed.todo_list_id or not str(parsed.todo_list_id).strip():
                raise ValueError(
                    "Incorrect format for remove_task: "
                    + "missing required parameter: "
                    + "todo_list_id (todo list id)"
                )

            target_list_id = str(parsed.todo_list_id).strip()

        task_removed = False
        new_lists_for_remove: list[TodoList] = []

        for todo_list in existing:
            if str(todo_list.id) != target_list_id:
                new_lists_for_remove.append(todo_list)
                continue

            try:
                new_lists_for_remove.append(
                    todo_remove_task(todo_list, task_id)
                )
                task_removed = True
            except ValueError:
                # Assumes ValueError means that the task was not found
                # in this particular todo list.
                new_lists_for_remove.append(todo_list)

        if not task_removed:
            raise ValueError(f"Task not found: {task_id}")

        todo_lists = new_lists_for_remove


    elif parsed.action == "mark_completed":
        if not parsed.task_id or not str(parsed.task_id).strip():
            raise ValueError(
                "Incorrect format for mark_completed: "
                + "missing required parameter: task_id"
            )

        from core.graph.todo_list import (
            mark_completed as todo_mark_completed,
        )

        task_id = str(parsed.task_id).strip()
        existing = normalize_todo_lists(todo_lists)

        if not existing:
            raise ValueError("No todo lists exist")

        if len(existing) == 1:
            target_list_id = str(existing[0].id)
        else:
            if not parsed.todo_list_id or not str(parsed.todo_list_id).strip():
                raise ValueError(
                    "Incorrect format for mark_completed: "
                    + "missing required parameter: "
                    + "todo_list_id (todo list id)"
                )

            target_list_id = str(parsed.todo_list_id).strip()

        task_marked = False
        new_lists_for_mark: list[TodoList] = []

        for todo_list in existing:
            if str(todo_list.id) != target_list_id:
                new_lists_for_mark.append(todo_list)
                continue

            try:
                new_lists_for_mark.append(
                    todo_mark_completed(
                        todo_list,
                        task_id,
                        completed=parsed.completed,
                    )
                )
                task_marked = True
            except ValueError:
                # Assumes ValueError means the task was not found
                # in the selected list.
                new_lists_for_mark.append(todo_list)

        if not task_marked:
            raise ValueError(f"Task not found: {task_id}")

        todo_lists = new_lists_for_mark

    elif parsed.action == "set_implementer":
        if not parsed.task_id or not str(parsed.task_id).strip():
            raise ValueError(
                "Incorrect format for set_implementer: "
                + "missing required parameter: task_id"
            )

        from core.graph.todo_list import (
            set_implementer as todo_set_implementer,
        )

        task_id = str(parsed.task_id).strip()
        implementer = getattr(parsed, "implementer", None)

        existing = normalize_todo_lists(todo_lists)

        if not existing:
            raise ValueError("No todo lists exist")

        if len(existing) == 1:
            target_list_id = str(existing[0].id)
        else:
            todo_list_id = getattr(parsed, "todo_list_id", None)

            if not isinstance(todo_list_id, (str, int)):
                raise ValueError(
                    "Incorrect format for set_implementer: "
                    + "missing required parameter: todo_list_id (todo list id)"
                )

            target_list_id = str(todo_list_id).strip()

            if not target_list_id:
                raise ValueError(
                    "Incorrect format for set_implementer: "
                    + "missing required parameter: todo_list_id (todo list id)"
                )

        task_updated = False
        new_lists_for_update: list[TodoList] = []

        for todo_list in existing:
            if str(todo_list.id) != target_list_id:
                new_lists_for_update.append(todo_list)
                continue

            try:
                new_lists_for_update.append(
                    todo_set_implementer(
                        todo_list,
                        task_id,
                        implementer=implementer,
                    )
                )
                task_updated = True
            except ValueError:
                # Assumes ValueError means the task was not found
                # in the selected list.
                new_lists_for_update.append(todo_list)

        if not task_updated:
            raise ValueError(f"Task not found: {task_id}")

        todo_lists = new_lists_for_update


    elif parsed.action == "set_deadline":
        if not parsed.task_id or not str(parsed.task_id).strip():
            raise ValueError(
                "Incorrect format for set_deadline: "
                + "missing required parameter: task_id"
            )

        from core.graph.todo_list import (
            set_deadline as todo_set_deadline,
        )

        task_id = str(parsed.task_id).strip()
        deadline = getattr(parsed, "deadline", None)

        existing = normalize_todo_lists(todo_lists)

        if not existing:
            raise ValueError("No todo lists exist")

        if len(existing) == 1:
            target_list_id = str(existing[0].id)
        else:
            todo_list_id = getattr(parsed, "todo_list_id", None)

            if not isinstance(todo_list_id, (str, int)):
                raise ValueError(
                    "Incorrect format for set_deadline: "
                    + "missing required parameter: "
                    + "todo_list_id (todo list id)"
                )

            target_list_id = str(todo_list_id).strip()

            if not target_list_id:
                raise ValueError(
                    "Incorrect format for set_deadline: "
                    + "missing required parameter: "
                    + "todo_list_id (todo list id)"
                )

        task_updated = False
        updated_todo_lists: list[TodoList] = []

        for todo_list in existing:
            if str(todo_list.id) != target_list_id:
                updated_todo_lists.append(todo_list)
                continue

            try:
                updated_todo_lists.append(
                    todo_set_deadline(
                        todo_list,
                        task_id,
                        deadline=deadline,
                    )
                )
                task_updated = True
            except ValueError:
                updated_todo_lists.append(todo_list)

        if not task_updated:
            raise ValueError(f"Task not found: {task_id}")

        todo_lists = updated_todo_lists


    elif parsed.action == "set_curator":
        if not parsed.task_id or not str(parsed.task_id).strip():
            raise ValueError(
                "Incorrect format for set_curator: "
                + "missing required parameter: task_id"
            )

        from core.graph.todo_list import (
            set_curator as todo_set_curator,
        )

        task_id = str(parsed.task_id).strip()
        curator = getattr(parsed, "curator", None)

        existing = normalize_todo_lists(todo_lists)

        if not existing:
            raise ValueError("No todo lists exist")

        if len(existing) == 1:
            target_list_id = str(existing[0].id)
        else:
            todo_list_id = getattr(parsed, "todo_list_id", None)

            if not isinstance(todo_list_id, (str, int)):
                raise ValueError(
                    "Incorrect format for set_curator: "
                    + "missing required parameter: "
                    + "todo_list_id (todo list id)"
                )

            target_list_id = str(todo_list_id).strip()

            if not target_list_id:
                raise ValueError(
                    "Incorrect format for set_curator: "
                    + "missing required parameter: "
                    + "todo_list_id (todo list id)"
                )

        task_updated = False
        curator_updated_lists: list[TodoList] = []

        for todo_list in existing:
            if str(todo_list.id) != target_list_id:
                curator_updated_lists.append(todo_list)
                continue

            try:
                curator_updated_lists.append(
                    todo_set_curator(
                        todo_list,
                        task_id,
                        curator=curator,
                    )
                )
                task_updated = True
            except ValueError:
                # Assumes ValueError means the task was not found
                # in the selected list.
                curator_updated_lists.append(todo_list)

        if not task_updated:
            raise ValueError(f"Task not found: {task_id}")

        todo_lists = curator_updated_lists


    elif parsed.action == "set_todo_list_title":
        todo_list_id_value = getattr(parsed, "todo_list_id", None)

        if not isinstance(todo_list_id_value, (str, int)):
            raise ValueError(
                "Incorrect format for set_todo_list_title: "
                + "missing required parameter: todo_list_id"
            )

        todo_list_id = str(todo_list_id_value).strip()

        if not todo_list_id:
            raise ValueError(
                "Incorrect format for set_todo_list_title: "
                + "missing required parameter: todo_list_id"
            )

        from core.graph.todo_list import (
            set_todo_list_title as todo_set_todo_list_title,
        )

        existing = normalize_todo_lists(todo_lists)

        if not existing:
            raise ValueError("No todo lists exist")

        new_title = getattr(parsed, "title", None)
        title_updated = False
        titled_todo_lists: list[TodoList] = []

        for todo_list in existing:
            if str(todo_list.id) != todo_list_id:
                titled_todo_lists.append(todo_list)
                continue

            try:
                titled_todo_lists.append(
                    todo_set_todo_list_title(
                        todo_list,
                        title=new_title,
                    )
                )
                title_updated = True
            except ValueError:
                # Assumes ValueError means the todo list could not be updated.
                titled_todo_lists.append(todo_list)

        if not title_updated:
            raise ValueError(f"Todo list not found: {todo_list_id}")

        todo_lists = titled_todo_lists


    elif (
        parsed.action == "replace_graph"
        and parsed.units is not None
        and parsed.connections is not None
    ):
        for u in parsed.units:
            raw_params = u.get("params")
            params: dict[str, JSONValue] = (
                raw_params.copy() if isinstance(raw_params, dict) else {}
            )

            unit_entry: dict[str, JSONValue] = {
                "id": str(u.get("id") or ""),
                "type": str(u.get("type") or "Unit"),
                "controllable": bool(u.get("controllable", False)),
                "params": params,
            }

            name_val = u.get("name")
            if name_val is not None and str(name_val).strip():
                unit_entry["name"] = str(name_val).strip()

            units.append(unit_entry)


        for c in parsed.connections:
            from_val = c.get("from") or c.get("from_id")
            to_val = c.get("to") or c.get("to_id")

            if from_val is None or to_val is None:
                continue

            new_edge: dict[str, JSONValue] = {
                "from": str(from_val),
                "to": str(to_val),
                "from_port": str(c.get("from_port") or "0"),
                "to_port": str(c.get("to_port") or "0"),
            }

            connection_type = c.get("connection_type")
            if connection_type is not None:
                new_edge["connection_type"] = str(connection_type)

            connections.append(new_edge)


        _assert_no_duplicate_connections(connections)

    # Preserve code_blocks and layout for units that still exist (or use from edit when replace_graph from import)
    final_unit_ids: set[str] = {
        unit_id
        for unit in units
        if isinstance(unit_id := unit.get("id"), str) and unit_id
    }

    raw_edit_code_blocks = edit.get("code_blocks")

    if (
        parsed.action == "replace_graph"
        and isinstance(raw_edit_code_blocks, list)
    ):
        code_blocks: list[dict[str, JSONValue]] = [
            cb
            for item in raw_edit_code_blocks
            if isinstance(item, dict)
            and isinstance(cb_id := item.get("id"), str)
            and cb_id in final_unit_ids
            for cb in [item]
        ]
    else:
        raw_current_code_blocks = current.get("code_blocks")

        code_blocks = [
            cb
            for item in (
                raw_current_code_blocks
                if isinstance(raw_current_code_blocks, list)
                else []
            )
            if isinstance(item, dict)
            and isinstance(cb_id := item.get("id"), str)
            and cb_id in final_unit_ids
            for cb in [item]
        ]

    if add_code_block_payload is not None:
        payload_id = add_code_block_payload.get("id")

        code_blocks = [
            cb
            for cb in code_blocks
            if cb.get("id") != payload_id
        ]
        code_blocks.append(add_code_block_payload)

    code_blocks.extend(add_oracle_code_blocks)
    code_blocks.extend(add_pyflow_code_blocks)
    code_blocks.extend(add_node_red_code_blocks)
    code_blocks.extend(add_n8n_code_blocks)

    raw_edit_layout = edit.get("layout")

    if (
        parsed.action == "replace_graph"
        and isinstance(raw_edit_layout, dict)
    ):
        layout: dict[str, JSONValue] = {
            key: value
            for key, value in raw_edit_layout.items()
            if key in final_unit_ids
        }
    else:
        raw_current_layout = current.get("layout")

        layout = (
            raw_current_layout.copy()
            if isinstance(raw_current_layout, dict)
            else {}
        )

        if (
            parsed.action == "replace_unit"
            and parsed.find_unit is not None
            and parsed.replace_with is not None
        ):
            old_id = parsed.find_unit.id
            new_id = parsed.replace_with.id

            if old_id in layout and new_id not in layout:
                layout[new_id] = layout[old_id]

        layout = {
            key: value
            for key, value in layout.items()
            if key in final_unit_ids
        }

    # Registry → Graph: ensure every unit has input_ports and output_ports from registry
    for u in units:
        _ensure_unit_ports_from_registry(u)

    unit_values: list[JSONValue] = [
        unit
        for unit in units
    ]

    connection_values: list[JSONValue] = [
        connection
        for connection in connections
    ]

    result: dict[str, JSONValue] = {
        "environment_type": env_type,
        "units": unit_values,
        "connections": connection_values,
    }

    if code_blocks:
        result["code_blocks"] = [
            code_block
            for code_block in code_blocks
        ]

    if layout:
        result["layout"] = layout

    # Prefer edit payload so imported graphs keep their origin format.
    edit_origin_format = edit.get("origin_format")

    if isinstance(edit_origin_format, str) and edit_origin_format.strip():
        result["origin_format"] = edit_origin_format.strip()
    else:
        current_origin_format = current.get("origin_format")
        if current_origin_format is not None:
            result["origin_format"] = current_origin_format

    current_environments = current.get("environments")
    if current_environments is not None:
        result["environments"] = current_environments

    edit_origin = edit.get("origin")
    current_origin = current.get("origin")

    if edit_origin is not None:
        result["origin"] = edit_origin
    elif current_origin is not None:
        result["origin"] = current_origin

    edit_runtime = edit.get("runtime")
    current_runtime = current.get("runtime")

    if edit_runtime is not None:
        result["runtime"] = edit_runtime
    elif current_runtime is not None:
        result["runtime"] = current_runtime

    # Prefer edit payload so imported graphs keep their comments and metadata.
    edit_comments = edit.get("comments")

    if isinstance(edit_comments, list):
        result["comments"] = [
            comment
            for comment in edit_comments
        ]
    elif comments:
        result["comments"] = [
            comment
            for comment in comments
        ]

    edit_metadata = edit.get("metadata")

    if isinstance(edit_metadata, dict):
        result["metadata"] = edit_metadata.copy()
    else:
        current_metadata = current.get("metadata")
        if current_metadata is not None:
            result["metadata"] = current_metadata

    edit_todo_lists = edit.get("todo_lists")

    if isinstance(edit_todo_lists, list):
        result["todo_lists"] = todo_lists_to_list(edit_todo_lists)
    elif todo_lists or current.get("todo_lists") is not None:
        result["todo_lists"] = todo_lists_to_list(todo_lists)

    return result
