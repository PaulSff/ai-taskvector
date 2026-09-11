"""
Graph edit schema and apply logic for Process agent.
Edits are applied to a graph dict; then normalizer.to_process_graph(updated) yields canonical ProcessGraph.
"""

import datetime
from pathlib import Path
from uuid import uuid4

from core.graph.pipeline_builder import (
    CANONICAL_JOIN_ID,
    CANONICAL_SWITCH_ID,
    ensure_canonical_topology,
    ensure_llm_canonical_topology,
    pipeline_wiring_guideline_message,
)
from core.graph.pipeline_templates import (
    load_pipeline_template,
    merge_pipeline_into_graph,
)
from core.graph.todo_list import (
    normalize_todo_lists,
)
from core.graph.utils import (
    assert_no_duplicate_connections,
    coding_is_allowed,
    default_workflow_designer_prompt_path,
    duplicate_connection_exists,
    ensure_unit_ports_from_registry,
    get_string_list,
    language_for_origin,
    reject_custom_code_unit_if_disabled,
    validate_connect_disconnect,
)
from core.normalizer.runtime_detector import runtime_label
from core.schemas.agent_node import (
    LLM_AGENT_NODE_TYPES,
    RL_AGENT_NODE_TYPES,
    RL_GYM_NODE_TYPE,
)
from core.schemas.graph_edit_api import (
    GraphEdit,
    GraphEditCodeBlock,
    GraphEditPipeline,
)
from core.schemas.primitives import JsonValue
from core.schemas.process_graph import (
    CodeBlock,
    Comment,
    Connection,
    NodePosition,
    ProcessGraph,
    TodoList,
    Unit,
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
from units.n8n import get_n8n_template, get_n8n_types
from units.node_red import get_node_red_template, get_node_red_types
from units.pyflow import get_pyflow_template, get_pyflow_types
from units.registry import get_unit_spec

# Pipeline types: RLGym, RLOracle, RLSet, LLMSet. Not graph "units" — they describe a training/serving pipeline.
# Use add_pipeline with "pipeline" payload. Unit types (Source, Valve, RLAgent, LLMAgent, etc.) use add_unit.
PIPELINE_TYPES: frozenset[str] = frozenset(
    [RL_GYM_NODE_TYPE, "RLOracle", "RLSet", "LLMSet"]
)

DEFAULT_LANGUAGE_FOR_ORIGIN: str = "python"


def apply_graph_edit(
    current: ProcessGraph,
    edit: GraphEdit,
) -> ProcessGraph:
    """
    Apply a single graph edit to the current ProcessGraph.

    Returns a new ProcessGraph and raises ValueError for invalid edits.
    """
    if edit.action == "import_workflow":
        raise ValueError(
            "import_workflow must be resolved via apply_workflow_edits (batch_edits)"
        )

    if edit.action == "add_environment":
        env_id = (edit.env_id or "").strip().lower()

        if not env_id:
            raise ValueError(
                "add_environment requires env_id (e.g. thermodynamic, data_bi)"
            )

        from units.env_loaders import known_environment_tags

        known = known_environment_tags()

        if env_id not in known:
            raise ValueError(
                f"Unknown environment: {env_id!r}. Known: {sorted(known)}"
            )

        graph = current.model_copy(deep=True)
        environments = set(graph.environments or ())
        environments.add(env_id)
        graph.environments = sorted(environments)

        return graph

    graph = current.model_copy(deep=True)

    add_code_block_payload: GraphEditCodeBlock | None = None
    add_oracle_code_blocks: list[CodeBlock] = []
    add_pyflow_code_blocks: list[CodeBlock] = []
    add_node_red_code_blocks: list[CodeBlock] = []
    add_n8n_code_blocks: list[CodeBlock] = []

    comments: list[Comment] = list(graph.comments or [])
    todo_lists: list[TodoList] = list(graph.todo_lists)

    env_type = graph.environment_type
    units: list[Unit] = list(graph.units)
    connections: list[Connection] = list(graph.connections)

    # Validate and normalize pipeline-related edits.
    #
    # LLMSet, RLSet, RLGym, and RLOracle are pipelines and should use
    # add_pipeline. If an add_unit edit carries one of those types, normalize
    # it into a GraphEditPipeline so the rest of this block handles it uniformly.

    p: GraphEditPipeline | None = None

    if edit.action == "add_pipeline":
        if edit.pipeline is None:
            raise ValueError("add_pipeline requires pipeline")

        p = edit.pipeline

    elif (
        edit.action == "add_unit"
        and edit.unit is not None
        and edit.unit.type in PIPELINE_TYPES
    ):
        unit = edit.unit

        p = GraphEditPipeline(
            id=unit.id,
            type=unit.type,
            params=dict(unit.params),
        )

    if p is not None:
        # RLAgent and LLMAgent are graph units, not pipelines.
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

        if any(existing.id == p.id for existing in units):
            raise ValueError(f"Unit id already exists: {p.id}")

        if p.type == RL_GYM_NODE_TYPE:
            # Full training setup for the runtime:
            # Join, StepRewards, Switch, StepDriver, and Split.
            if get_unit_spec(RL_GYM_NODE_TYPE) is None:
                try:
                    from units.pipelines.rl_gym import register_rl_gym

                    register_rl_gym()
                except (ImportError, AttributeError):
                    pass

            raw_obs_ids = p.params.get("observation_source_ids")
            raw_act_ids = p.params.get("action_target_ids")

            obs_ids = (
                [str(value) for value in raw_obs_ids]
                if isinstance(raw_obs_ids, list)
                else []
            )
            act_ids = (
                [str(value) for value in raw_act_ids]
                if isinstance(raw_act_ids, list)
                else []
            )

            ensure_canonical_topology(
                units,
                connections,
                obs_ids,
                act_ids,
                include_training_units=True,
            )

            units.append(
                Unit(
                    id=p.id,
                    type=RL_GYM_NODE_TYPE,
                    controllable=False,
                    params=dict(p.params),
                )
            )

        elif p.type == "RLOracle":
            raw_adapter_config = p.params.get("adapter_config")

            if isinstance(raw_adapter_config, dict):
                adapter_config: dict[str, JsonValue] = raw_adapter_config.copy()
            else:
                adapter_config = p.params.copy()

            raw_origin = current.origin

            oracle_origin: dict[str, JsonValue] = (
                raw_origin.model_dump(mode="json")
                if raw_origin is not None
                else {}
            )

            lang = language_for_origin(oracle_origin) or DEFAULT_LANGUAGE_FOR_ORIGIN

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

            json_observation_source_ids: list[JsonValue] = [
                value for value in oracle_obs_ids
            ]

            json_action_target_ids: list[JsonValue] = [
                value for value in oracle_act_ids
            ]

            adapter_config["observation_source_ids"] = (
                json_observation_source_ids
            )
            adapter_config["action_target_ids"] = (
                json_action_target_ids
            )

            ensure_canonical_topology(
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

            add_oracle_code_blocks.extend(
                CodeBlock.model_validate(code_block)
                for code_block in cbs
            )

        elif p.type == "RLSet":
            # Full RL agent set: Join, Switch, RLAgent unit, wiring,
            # and generated code blocks. Uses the same parameters as RLAgent.

            raw_rlset_obs_ids = p.params.get("observation_source_ids")
            raw_rlset_act_ids = p.params.get("action_target_ids")

            rlset_obs_ids: list[str] = (
                [str(value) for value in raw_rlset_obs_ids]
                if isinstance(raw_rlset_obs_ids, list)
                else []
            )

            rlset_act_ids: list[str] = (
                [str(value) for value in raw_rlset_act_ids]
                if isinstance(raw_rlset_act_ids, list)
                else []
            )

            ensure_canonical_topology(
                units,
                connections,
                rlset_obs_ids,
                rlset_act_ids,
                include_training_units=False,
            )

            raw_rl_model_path = p.params.get("model_path")
            rl_model_path: object = (
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

            rl_agent_params: dict[str, object] = {
                key: value
                for key, value in p.params.items()
                if key not in {
                    "observation_source_ids",
                    "action_target_ids",
                }
            }
            rl_agent_params["model_path"] = rl_model_path

            units.append(
                Unit(
                    id=p.id,
                    type="RLAgent",
                    controllable=False,
                    params=rl_agent_params,
                )
            )

            connections.append(
                Connection.model_validate(
                    {
                        "from": CANONICAL_JOIN_ID,
                        "to": p.id,
                        "from_port": "0",
                        "to_port": "0",
                    }
                )
            )

            connections.append(
                Connection.model_validate(
                    {
                        "from": p.id,
                        "to": CANONICAL_SWITCH_ID,
                        "from_port": "0",
                        "to_port": "0",
                    }
                )
            )

            raw_rlset_origin = current.origin
            rlset_origin: dict[str, JsonValue] = (
                raw_rlset_origin.model_dump(mode="json")
                if raw_rlset_origin is not None
                else {}
            )

            lang = language_for_origin(rlset_origin) or "python"

            if lang == "python":
                code_src = render_rl_agent_predict_py(
                    rl_inference_url,
                    rlset_obs_ids,
                )

                add_oracle_code_blocks.append(
                    CodeBlock(
                        id=p.id,
                        language="python",
                        source=code_src,
                    )
                )

            elif runtime_label(current) == "n8n":
                code_src = render_rl_agent_predict_n8n(
                    rl_inference_url,
                    rlset_obs_ids,
                )

                add_oracle_code_blocks.append(
                    CodeBlock(
                        id=p.id,
                        language="javascript",
                        source=code_src,
                    )
                )

            else:
                code_src = render_rl_agent_predict_js(
                    rl_inference_url,
                    rlset_obs_ids,
                )

                add_oracle_code_blocks.append(
                    CodeBlock(
                        id=p.id,
                        language="javascript",
                        source=code_src,
                    )
                )

        elif p.type == "LLMSet":
            raw_obs_ids = p.params.get("observation_source_ids")
            raw_act_ids = p.params.get("action_target_ids")

            llm_obs_ids = (
                [str(value) for value in raw_obs_ids]
                if isinstance(raw_obs_ids, list)
                else []
            )
            llm_act_ids = (
                [str(value) for value in raw_act_ids]
                if isinstance(raw_act_ids, list)
                else []
            )

            pipeline_params: dict[str, object] = {
                key: value
                for key, value in p.params.items()
                if key not in {
                    "observation_source_ids",
                    "action_target_ids",
                }
            }

            repo_root = Path(__file__).resolve().parent.parent.parent
            template = load_pipeline_template(
                "LLMSet",
                base_path=repo_root,
            )

            if template is not None:
                existing_ids = {unit.id for unit in units}

                merge_pipeline_into_graph(
                    units,
                    connections,
                    template,
                    p.id,
                    dict(p.params),
                    llm_obs_ids,
                    llm_act_ids,
                    existing_ids,
                )
            else:
                units.append(
                    Unit(
                        id=p.id,
                        type="LLMAgent",
                        controllable=False,
                        params=pipeline_params,
                    )
                )

                raw_template_path = p.params.get("template_path")
                if not isinstance(raw_template_path, str) or not raw_template_path:
                    raw_template_path = p.params.get("prompt_template_path")

                prompt_template_path = (
                    raw_template_path
                    if isinstance(raw_template_path, str) and raw_template_path
                    else str(default_workflow_designer_prompt_path())
                )

                ensure_llm_canonical_topology(
                    units,
                    connections,
                    llm_obs_ids,
                    llm_act_ids,
                    p.id,
                    prompt_template_path=prompt_template_path,
                )

            inference_url = str(
                p.params.get(
                    "inference_url",
                    "http://127.0.0.1:8001/predict",
                )
            )

            system_prompt = str(
                p.params.get(
                    "system_prompt",
                    (
                        "You are a control agent. Given observations, output a "
                        "JSON object with an 'action' key containing a list "
                        "of numbers."
                    ),
                )
            )

            user_prompt_template = str(
                p.params.get(
                    "user_prompt_template",
                    (
                        "Observations: {observation_json}. Output only a JSON "
                        "object with key 'action' and value a list of numbers."
                    ),
                )
            )

            model_name = str(p.params.get("model_name", "llama3.2"))
            provider = str(p.params.get("provider", "ollama"))
            host = str(p.params.get("host", ""))

            raw_origin = current.origin
            llm_origin: dict[str, JsonValue] = (
                raw_origin.model_dump(mode="json")
                if raw_origin is not None
                else {}
            )

            lang = language_for_origin(llm_origin) or DEFAULT_LANGUAGE_FOR_ORIGIN
            runtime = runtime_label(current)

            if lang == "python":
                language = "python"
                source = render_llm_agent_predict_py(
                    inference_url=inference_url,
                    observation_source_ids=llm_obs_ids,
                    system_prompt=system_prompt,
                    user_prompt_template=user_prompt_template,
                    model_name=model_name,
                    provider=provider,
                    host=host,
                )
            elif runtime == "n8n":
                language = "javascript"
                source = render_llm_agent_predict_n8n(
                    inference_url=inference_url,
                    observation_source_ids=llm_obs_ids,
                    system_prompt=system_prompt,
                    user_prompt_template=user_prompt_template,
                    model_name=model_name,
                    provider=provider,
                    host=host,
                )
            else:
                language = "javascript"
                source = render_llm_agent_predict_js(
                    inference_url=inference_url,
                    observation_source_ids=llm_obs_ids,
                    system_prompt=system_prompt,
                    user_prompt_template=user_prompt_template,
                    model_name=model_name,
                    provider=provider,
                    host=host,
                )

            add_oracle_code_blocks.append(
                CodeBlock(
                    id=p.id,
                    language=language,
                    source=source,
                )
            )

        # System comment with wiring guidelines when any canonical pipeline is added.
        comment_id = f"comment_{uuid4().hex[:8]}"
        created_at = datetime.datetime.now(datetime.UTC).strftime(
            "%y-%m-%d-%H%M%S"
        )

        comments.append(
            Comment(
                id=comment_id,
                info=pipeline_wiring_guideline_message(p.type),
                commenter="system",
                created_at=created_at,
            )
        )

    elif edit.action == "add_unit" and edit.unit is not None:
        u = edit.unit

        if any(existing_unit.id == u.id for existing_unit in units):
            raise ValueError(f"Unit id already exists: {u.id}")

        if get_unit_spec(u.type) is None and not coding_is_allowed():
            raise ValueError("Invalid unit. Use units from the Units Library.")

        reject_custom_code_unit_if_disabled(u.type)

        if u.type in RL_AGENT_NODE_TYPES:
            raw_model_path = u.params.get("model_path")
            model_path: object = (
                raw_model_path if raw_model_path is not None else ""
            )

            source_ids: set[str] = set()
            target_ids: set[str] = set()

            for connection in connections:
                if connection.to_id == u.id:
                    source_ids.add(connection.from_id)

                if connection.from_id == u.id:
                    target_ids.add(connection.to_id)

            rl_obs_ids = get_string_list(
                u.params,
                "observation_source_ids",
                source_ids,
            )
            rl_act_ids = get_string_list(
                u.params,
                "action_target_ids",
                target_ids,
            )

            ensure_canonical_topology(
                units,
                connections,
                rl_obs_ids or [],
                rl_act_ids or [],
                include_training_units=False,
            )

            inference_url = str(
                u.params.get("inference_url")
                or "http://127.0.0.1:8000/predict"
            )

            rl_params: dict[str, object] = {
                "model_path": model_path,
                **{
                    key: value
                    for key, value in u.params.items()
                    if key not in {
                        "observation_source_ids",
                        "action_target_ids",
                    }
                },
            }

            units.append(
                Unit(
                    id=u.id,
                    type=u.type,
                    controllable=False,
                    params=rl_params,
                    name=u.name,
                )
            )

            connections.append(
                Connection.model_validate(
                    {
                        "from": CANONICAL_JOIN_ID,
                        "to": u.id,
                        "from_port": "0",
                        "to_port": "0",
                    }
                )
            )
            connections.append(
                Connection.model_validate(
                    {
                        "from": u.id,
                        "to": CANONICAL_SWITCH_ID,
                        "from_port": "0",
                        "to_port": "0",
                    }
                )
            )

            origin = (
                current.origin.model_dump(mode="json")
                if current.origin is not None
                else {}
            )

            lang = language_for_origin(origin) or "python"

            if lang == "python":
                code_src = render_rl_agent_predict_py(
                    inference_url,
                    rl_obs_ids or [],
                )
                add_oracle_code_blocks.append(
                    CodeBlock(
                        id=u.id,
                        language="python",
                        source=code_src,
                    )
                )
            elif runtime_label(current) == "n8n":
                code_src = render_rl_agent_predict_n8n(
                    inference_url,
                    rl_obs_ids or [],
                )
                add_oracle_code_blocks.append(
                    CodeBlock(
                        id=u.id,
                        language="javascript",
                        source=code_src,
                    )
                )
            else:
                code_src = render_rl_agent_predict_js(
                    inference_url,
                    rl_obs_ids or [],
                )
                add_oracle_code_blocks.append(
                    CodeBlock(
                        id=u.id,
                        language="javascript",
                        source=code_src,
                    )
                )

        elif u.type in LLM_AGENT_NODE_TYPES:
            source_ids = {
                connection.from_id
                for connection in connections
                if connection.to_id == u.id
            }

            target_ids = {
                connection.to_id
                for connection in connections
                if connection.from_id == u.id
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

            ensure_canonical_topology(
                units,
                connections,
                obs_ids or [],
                act_ids or [],
                include_training_units=False,
            )

            inference_url = str(
                u.params.get("inference_url")
                or "http://127.0.0.1:8001/predict"
            )
            system_prompt = str(
                u.params.get("system_prompt")
                or (
                    "You are a control agent. Given observations, output a "
                    "JSON object with an 'action' key containing a list of numbers."
                )
            )
            user_prompt_template = str(
                u.params.get("user_prompt_template")
                or (
                    "Observations: {observation_json}. Output only a JSON object "
                    "with key 'action' and value a list of numbers."
                )
            )
            model_name = str(u.params.get("model_name") or "llama3.2")
            provider = str(u.params.get("provider") or "ollama")
            host = str(u.params.get("host") or "")

            llm_params: dict[str, object] = {
                key: value
                for key, value in u.params.items()
                if key not in {
                    "observation_source_ids",
                    "action_target_ids",
                }
            }

            units.append(
                Unit(
                    id=u.id,
                    type=u.type,
                    controllable=False,
                    params=llm_params,
                    name=u.name,
                )
            )

            connections.append(
                Connection.model_validate(
                    {
                        "from": CANONICAL_JOIN_ID,
                        "to": u.id,
                        "from_port": "0",
                        "to_port": "0",
                    }
                )
            )
            connections.append(
                Connection.model_validate(
                    {
                        "from": u.id,
                        "to": CANONICAL_SWITCH_ID,
                        "from_port": "0",
                        "to_port": "0",
                    }
                )
            )

            origin = (
                current.origin.model_dump(mode="json")
                if current.origin is not None
                else {}
            )

            lang = language_for_origin(origin) or "python"

            if lang == "python":
                code_src = render_llm_agent_predict_py(
                    inference_url,
                    obs_ids or [],
                    system_prompt,
                    user_prompt_template,
                    model_name,
                    provider,
                    host,
                )
                add_oracle_code_blocks.append(
                    CodeBlock(
                        id=u.id,
                        language="python",
                        source=code_src,
                    )
                )
            elif runtime_label(current) == "n8n":
                code_src = render_llm_agent_predict_n8n(
                    inference_url,
                    obs_ids or [],
                    system_prompt,
                    user_prompt_template,
                    model_name,
                    provider,
                    host,
                )
                add_oracle_code_blocks.append(
                    CodeBlock(
                        id=u.id,
                        language="javascript",
                        source=code_src,
                    )
                )
            else:
                code_src = render_llm_agent_predict_js(
                    inference_url,
                    obs_ids or [],
                    system_prompt,
                    user_prompt_template,
                    model_name,
                    provider,
                    host,
                )
                add_oracle_code_blocks.append(
                    CodeBlock(
                        id=u.id,
                        language="javascript",
                        source=code_src,
                    )
                )

        else:
            units.append(
                Unit(
                    id=u.id,
                    type=u.type,
                    controllable=u.controllable,
                    params=dict(u.params),
                    name=(
                        u.name.strip()
                        if u.name is not None and u.name.strip()
                        else None
                    ),
                )
            )

            if u.type in get_pyflow_types():
                entry = get_pyflow_template(u.type)
                if entry and entry.get("code_template"):
                    add_pyflow_code_blocks.append(
                        CodeBlock(
                            id=u.id,
                            language="python",
                            source=str(entry["code_template"]),
                        )
                    )

            if (
                runtime_label(current) == "node_red"
                and u.type in get_node_red_types()
            ):
                entry = get_node_red_template(u.type)
                if entry and entry.get("code_template"):
                    add_node_red_code_blocks.append(
                        CodeBlock(
                            id=u.id,
                            language="javascript",
                            source=str(entry["code_template"]),
                        )
                    )

            if runtime_label(current) == "n8n" and u.type in get_n8n_types():
                entry = get_n8n_template(u.type)
                if entry and entry.get("code_template"):
                    add_n8n_code_blocks.append(
                        CodeBlock(
                            id=u.id,
                            language="javascript",
                            source=str(entry["code_template"]),
                        )
                    )


    elif edit.action == "remove_unit":
        if edit.unit_id is None:
            raise ValueError(
                "Incorrect format for remove_unit: missing required parameter: unit_id"
            )

        uid = edit.unit_id

        if not any(unit.id == uid for unit in units):
            raise ValueError(f"Unit id does not exist: {uid}")

        units = [
            unit
            for unit in units
            if unit.id != uid
        ]

        connections = [
            connection
            for connection in connections
            if connection.from_id != uid and connection.to_id != uid
        ]

    elif edit.action == "set_params":
        uid = edit.id

        if not uid:
            raise ValueError(
                "Incorrect format for set_params: missing required parameter: id"
            )

        if edit.new_params is None:
            raise ValueError(
                "Incorrect format for set_params: missing or invalid new_params (must be a JSON object)"
            )

        unit = next((unit for unit in units if unit.id == uid), None)

        if unit is None:
            from agents.prompts import (
                WORKFLOW_DESIGNER_SET_PARAMS_UNIT_NOT_FOUND_ERROR,
            )

            raise ValueError(
                WORKFLOW_DESIGNER_SET_PARAMS_UNIT_NOT_FOUND_ERROR.format(
                    unit_id=uid
                )
            )

        unit.params = {
            **unit.params,
            **edit.new_params,
        }

    elif edit.action == "connect":
        validate_connect_disconnect(edit)

        from_id = str(edit.from_id)
        to_id = str(edit.to_id)

        unit_ids = {unit.id for unit in units}

        if from_id not in unit_ids:
            raise ValueError(f"Unit id does not exist: {from_id}")

        if to_id not in unit_ids:
            raise ValueError(f"Unit id does not exist: {to_id}")

        from_port = (
            str(edit.from_port)
            if edit.from_port is not None
            else "0"
        )
        to_port = (
            str(edit.to_port)
            if edit.to_port is not None
            else "0"
        )

        if duplicate_connection_exists(
            connections,
            from_id=from_id,
            to_id=to_id,
            from_port=from_port,
            to_port=to_port,
        ):
            raise ValueError(
                f"Duplicate connection: from={from_id!r}, "
                + f"to={to_id!r}, "
                + f"from_port={from_port!r}, "
                + f"to_port={to_port!r}"
            )

        connections.append(
            Connection.model_validate(
                {
                    "from": from_id,
                    "to": to_id,
                    "from_port": from_port,
                    "to_port": to_port,
                }
            )
        )


    elif edit.action == "disconnect":
        validate_connect_disconnect(edit)

        from_id = str(edit.from_id)
        to_id = str(edit.to_id)

        from_port = (
            str(edit.from_port)
            if edit.from_port is not None
            else None
        )
        to_port = (
            str(edit.to_port)
            if edit.to_port is not None
            else None
        )

        def matches_connection(connection: Connection) -> bool:
            return (
                connection.from_id == from_id
                and connection.to_id == to_id
                and (
                    from_port is None
                    or connection.from_port == from_port
                )
                and (
                    to_port is None
                    or connection.to_port == to_port
                )
            )

        if not any(matches_connection(connection) for connection in connections):
            raise ValueError(
                f"Connection does not exist: from={edit.from_id}, to={edit.to_id}"
                + (
                    f" (from_port={from_port}, to_port={to_port})"
                    if from_port is not None or to_port is not None
                    else ""
                )
            )

        connections = [
            connection
            for connection in connections
            if not matches_connection(connection)
        ]

    elif edit.action == "replace_unit":
        if edit.find_unit is None or edit.replace_with is None:
            raise ValueError(
                "Incorrect format for replace_unit: missing required parameter(s): find_unit, replace_with"
            )

        old_id = edit.find_unit.id
        replacement = edit.replace_with
        new_id = replacement.id

        if not any(unit.id == old_id for unit in units):
            raise ValueError(f"Unit id does not exist: {old_id}")

        if old_id != new_id and any(unit.id == new_id for unit in units):
            raise ValueError(f"Unit id already exists: {new_id}")

        if (
            get_unit_spec(replacement.type) is None
            and not coding_is_allowed()
        ):
            raise ValueError("Invalid unit. Use units from the Units Library.")

        reject_custom_code_unit_if_disabled(replacement.type)

        # Make a copy so this operation does not unexpectedly mutate the
        # Unit object stored in the edit request.
        new_unit: Unit = Unit.model_validate(
            replacement.model_dump(mode="python")
        )

        if new_unit.name is not None:
            stripped_name = new_unit.name.strip()
            new_unit.name = stripped_name or None

        # Replace the unit while preserving list order.
        units = [
            new_unit if unit.id == old_id else unit
            for unit in units
        ]

        # Reconnect edges to the replacement unit.
        for connection in connections:
            if connection.from_id == old_id:
                connection.from_id = new_id

            if connection.to_id == old_id:
                connection.to_id = new_id

    elif edit.action == "add_code_block":
        if not coding_is_allowed():
            raise ValueError("Invalid unit. Use units from the Units Library.")

        requested_code_block = edit.code_block
        if requested_code_block is None:
            raise ValueError(
                "Incorrect format for add_code_block: missing required parameter: code_block"
            )

        # `current` must be a ProcessGraph here.
        graph: ProcessGraph = current

        if not any(unit.id == requested_code_block.id for unit in graph.units):
            raise ValueError(f"Unit id does not exist: {requested_code_block.id}")

        if any(
            block.id == requested_code_block.id
            for block in graph.code_blocks
        ):
            raise ValueError(
                f"Code block already exists for unit id: {requested_code_block.id}"
            )

        raw_origin = graph.origin
        origin_data = (
            raw_origin.model_dump(mode="python")
            if raw_origin is not None
            else None
        )

        expected_lang = language_for_origin(origin_data)
        actual_lang = requested_code_block.language.strip().lower()

        if expected_lang is not None and actual_lang != expected_lang:
            raise ValueError(
                "Language must match origin runtime: "
                + f"expected '{expected_lang}', "
                + f"got '{requested_code_block.language}'"
            )

        new_code_block = CodeBlock.model_validate(
            requested_code_block.model_dump(mode="python")
        )
        new_code_block.language = actual_lang

        graph.code_blocks.append(new_code_block)


    elif edit.action == "add_comment":
        if not edit.info or not str(edit.info).strip():
            raise ValueError(
                "Incorrect format for add_comment: missing required parameter: info (non-empty string)"
            )

        comment = Comment(
            id=f"comment_{uuid4().hex[:8]}",
            info=str(edit.info).strip(),
            commenter=(
                str(edit.commenter).strip()
                if edit.commenter and str(edit.commenter).strip()
                else ""
            ),
            created_at=(
                datetime.datetime.now(datetime.UTC)
                .isoformat()
                .replace("+00:00", "Z")
            ),
        )

        comments.append(comment)

    elif edit.action == "remove_comment":
        raw_comment_id: object = getattr(edit, "comment_id", None)

        if raw_comment_id is None or not str(raw_comment_id).strip():
            raise ValueError(
                "Incorrect format for remove_comment: missing required parameter: comment_id"
            )

        comment_id = str(raw_comment_id).strip()

        if current.comments is None:
            raise ValueError(
                f"remove_comment: comment_id not found: {comment_id}"
            )

        before_len = len(current.comments)

        current.comments[:] = [
            comment
            for comment in current.comments
            if comment.id.strip() != comment_id
        ]

        if len(current.comments) == before_len:
            raise ValueError(
                f"remove_comment: comment_id not found: {comment_id}"
            )


    elif edit.action == "add_todo_list":
        existing_ids = {
            todo_list.id
            for todo_list in current.todo_lists
        }

        raw_list_id: object = getattr(edit, "id", None)

        if raw_list_id is not None and str(raw_list_id).strip():
            list_id = str(raw_list_id).strip()

            if list_id in existing_ids:
                raise ValueError(f"Todo list id already exists: {list_id}")
        else:
            index = 1
            list_id = f"todo_list_default_{index}"

            while list_id in existing_ids:
                index += 1
                list_id = f"todo_list_default_{index}"

        raw_title: object = getattr(edit, "title", None)
        title = (
            str(raw_title).strip()
            if raw_title is not None and str(raw_title).strip()
            else None
        )

        current.todo_lists.append(
            TodoList(
                id=list_id,
                title=title,
                tasks=[],
            )
        )

    elif edit.action == "remove_todo_list":
        if not edit.id or not str(edit.id).strip():
            raise ValueError(
                "Incorrect format for remove_todo_list: "
                + "missing required parameter: id"
            )

        target_id = str(edit.id).strip()

        existing = normalize_todo_lists(todo_lists)

        filtered_lists = [
            todo_list
            for todo_list in existing
            if str(todo_list.id) != target_id
        ]

        if len(filtered_lists) == len(existing):
            raise ValueError(f"Todo list not found: {target_id}")

        todo_lists = filtered_lists


    elif edit.action == "add_task":
        if not edit.text or not str(edit.text).strip():
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
            if not edit.todo_list_id or not str(edit.todo_list_id).strip():
                raise ValueError(
                    "Incorrect format for add_task: "
                    + "missing required parameter: todo_list_id (todo list id)"
                )

            target_list_id = str(edit.todo_list_id).strip()

        task_text = str(edit.text).strip()
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


    elif edit.action == "remove_task":
        if not edit.task_id or not str(edit.task_id).strip():
            raise ValueError(
                "Incorrect format for remove_task: "
                + "missing required parameter: task_id"
            )

        from core.graph.todo_list import (
            remove_task as todo_remove_task,
        )

        task_id = str(edit.task_id).strip()
        existing = normalize_todo_lists(todo_lists)

        if not existing:
            raise ValueError("No todo lists exist")

        if len(existing) == 1:
            target_list_id = str(existing[0].id)
        else:
            if not edit.todo_list_id or not str(edit.todo_list_id).strip():
                raise ValueError(
                    "Incorrect format for remove_task: "
                    + "missing required parameter: "
                    + "todo_list_id (todo list id)"
                )

            target_list_id = str(edit.todo_list_id).strip()

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


    elif edit.action == "mark_completed":
        if not edit.task_id or not str(edit.task_id).strip():
            raise ValueError(
                "Incorrect format for mark_completed: "
                + "missing required parameter: task_id"
            )

        from core.graph.todo_list import (
            mark_completed as todo_mark_completed,
        )

        task_id = str(edit.task_id).strip()
        existing = normalize_todo_lists(todo_lists)

        if not existing:
            raise ValueError("No todo lists exist")

        if len(existing) == 1:
            target_list_id = str(existing[0].id)
        else:
            if not edit.todo_list_id or not str(edit.todo_list_id).strip():
                raise ValueError(
                    "Incorrect format for mark_completed: "
                    + "missing required parameter: "
                    + "todo_list_id (todo list id)"
                )

            target_list_id = str(edit.todo_list_id).strip()

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
                        completed=edit.completed,
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

    elif edit.action == "set_implementer":
        if not edit.task_id or not str(edit.task_id).strip():
            raise ValueError(
                "Incorrect format for set_implementer: "
                + "missing required parameter: task_id"
            )

        from core.graph.todo_list import (
            set_implementer as todo_set_implementer,
        )

        task_id = str(edit.task_id).strip()
        implementer = getattr(edit, "implementer", None)

        existing = normalize_todo_lists(todo_lists)

        if not existing:
            raise ValueError("No todo lists exist")

        if len(existing) == 1:
            target_list_id = str(existing[0].id)
        else:
            todo_list_id = getattr(edit, "todo_list_id", None)

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


    elif edit.action == "set_deadline":
        if not edit.task_id or not str(edit.task_id).strip():
            raise ValueError(
                "Incorrect format for set_deadline: "
                + "missing required parameter: task_id"
            )

        from core.graph.todo_list import (
            set_deadline as todo_set_deadline,
        )

        task_id = str(edit.task_id).strip()
        deadline = getattr(edit, "deadline", None)

        existing = normalize_todo_lists(todo_lists)

        if not existing:
            raise ValueError("No todo lists exist")

        if len(existing) == 1:
            target_list_id = str(existing[0].id)
        else:
            todo_list_id = getattr(edit, "todo_list_id", None)

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


    elif edit.action == "set_curator":
        if not edit.task_id or not str(edit.task_id).strip():
            raise ValueError(
                "Incorrect format for set_curator: "
                + "missing required parameter: task_id"
            )

        from core.graph.todo_list import (
            set_curator as todo_set_curator,
        )

        task_id = str(edit.task_id).strip()
        curator = getattr(edit, "curator", None)

        existing = normalize_todo_lists(todo_lists)

        if not existing:
            raise ValueError("No todo lists exist")

        if len(existing) == 1:
            target_list_id = str(existing[0].id)
        else:
            todo_list_id = getattr(edit, "todo_list_id", None)

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


    elif edit.action == "set_todo_list_title":
        todo_list_id_value = getattr(edit, "todo_list_id", None)

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

        new_title = getattr(edit, "title", None)
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
        edit.action == "replace_graph"
        and edit.units is not None
        and edit.connections is not None
    ):
        # Replace the canonical unit and connection collections with validated
        # schema models.
        units = [
            Unit.model_validate(unit)
            for unit in edit.units
        ]

        connections = [
            Connection.model_validate(connection)
            for connection in edit.connections
            if (
                connection.get("from") is not None
                or connection.get("from_id") is not None
            )
            and (
                connection.get("to") is not None
                or connection.get("to_id") is not None
            )
        ]

        assert_no_duplicate_connections(connections)


    # Preserve code blocks and layout only for units that still exist.
    final_unit_ids: set[str] = {
        unit.id
        for unit in units
    }


    # ---------------------------------------------------------------------------
    # Code blocks
    # ---------------------------------------------------------------------------

    if edit.action == "replace_graph" and edit.code_blocks is not None:
        code_blocks: list[CodeBlock] = [
            CodeBlock.model_validate(
                edit_code_block.model_dump(mode="python")
            )
            for edit_code_block in edit.code_blocks
        ]
    else:
        code_blocks = [
            CodeBlock.model_validate(code_block)
            for code_block in current.code_blocks
        ]

    # Add code blocks from all supported sources.
    code_block_payloads: list[object] = [
        *add_oracle_code_blocks,
        *add_pyflow_code_blocks,
        *add_node_red_code_blocks,
        *add_n8n_code_blocks,
    ]

    code_block_payloads = (
        code_block_payloads
        + [add_code_block_payload]
        if add_code_block_payload is not None
        else code_block_payloads
    )

    for payload in code_block_payloads:
        validated_code_block = CodeBlock.model_validate(payload)

        # Replace an existing block with the same ID.
        code_blocks = [
            code_block
            for code_block in code_blocks
            if code_block.id != validated_code_block.id
        ]

        code_blocks = [
            *code_blocks,
            validated_code_block,
        ]

    # Remove blocks for units that no longer exist.
    # If multiple sources provide the same ID, keep the last one.
    deduplicated_code_blocks: dict[str, CodeBlock] = {}

    for code_block in code_blocks:
        if code_block.id in final_unit_ids:
            deduplicated_code_blocks[code_block.id] = code_block

    code_blocks = list(deduplicated_code_blocks.values())

    # ---------------------------------------------------------------------------
    # Layout
    # ---------------------------------------------------------------------------

    layout: dict[str, NodePosition] = {}

    if edit.action == "replace_graph" and edit.layout is not None:
        for unit_id, position in edit.layout.items():
            if unit_id in final_unit_ids:
                layout[unit_id] = NodePosition.model_validate(position)

    else:
        current_layout: dict[str, NodePosition] = current.layout or {}

        layout = {
            unit_id: NodePosition.model_validate(position)
            for unit_id, position in current_layout.items()
            if unit_id in final_unit_ids
        }

        if (
            edit.action == "replace_unit"
            and edit.find_unit is not None
            and edit.replace_with is not None
        ):
            old_id: str = edit.find_unit.id
            new_id: str = edit.replace_with.id

            if old_id in layout and new_id not in layout:
                old_position: NodePosition = layout[old_id]
                layout[new_id] = NodePosition(
                    x=old_position.x,
                    y=old_position.y,
                )

    # --------------------------------------------------------------------------
    # Registry → Graph
    # ---------------------------------------------------------------------------

    for unit in units:
        ensure_unit_ports_from_registry(unit)


    # ---------------------------------------------------------------------------
    # Preserve graph metadata
    # ---------------------------------------------------------------------------

    origin_format = (
        edit.format.strip()
        if edit.format is not None
        and edit.format.strip()
        else current.origin_format
    )

    environments = current.environments
    origin = current.origin
    runtime = current.runtime
    metadata = current.metadata

    # ---------------------------------------------------------------------------
    # Construct the ProcessGraph graph
    # ---------------------------------------------------------------------------

    result = ProcessGraph(
        environment_type=env_type,
        environments=environments,
        keep_alive=current.keep_alive,
        units=units,
        connections=connections,
        code_blocks=code_blocks,
        layout=layout or None,
        origin=origin,
        origin_format=origin_format,
        runtime=runtime,
        comments=comments,
        metadata=metadata,
        todo_lists=todo_lists,
        tabs=current.tabs,
    )

    return result
