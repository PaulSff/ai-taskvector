"""
Data normalizer: map raw input (dict, YAML, Node-RED) to canonical ProcessGraph and TrainingConfig.
All external formats flow through here so the rest of the stack sees one schema.

Unit types and the controllable flag are taken from the unit spec (units/registry.py).
For correct controllable detection when importing flows, ensure unit modules are registered
(e.g. at app startup: units.thermodynamic, units.env_agnostic, units.pipelines).
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, cast

import yaml

from core.normalizer.comfyui_import import (
    to_canonical_dict as _comfyui_to_canonical_dict,
)
from core.normalizer.idaes_import import to_canonical_dict as _idaes_to_canonical_dict
from core.normalizer.n8n_import import to_canonical_dict as _n8n_to_canonical_dict
from core.normalizer.node_red_import import (
    to_canonical_dict as _node_red_to_canonical_dict,
)
from core.normalizer.pyflow_import import to_canonical_dict as _pyflow_to_canonical_dict
from core.normalizer.runtime_detector import is_canonical_runtime
from core.normalizer.ryven_import import to_canonical_dict as _ryven_to_canonical_dict
from core.normalizer.shared import (
    as_object,
    canonical_unit_type,
    ensure_list_connections,
    infer_environments_from_unit_types,
    to_json_value,
)
from core.normalizer.system_comments import make_canonical_system_comment
from core.normalizer.template_import import (
    to_canonical_dict as _template_to_canonical_dict,
)
from core.normalizer.utils import (
    ensure_env_agnostic_units_registered,
    ensure_environment_units_registered,
    ensure_environments_units_registered,
    load_yaml_object,
    parse_keep_alive,
    parse_port_specs,
    require_json_document,
    require_json_object,
)
from core.schemas.primitives import (
    FormatProcess,
    FormatTraining,
    JsonArray,
    JsonObject,
    JsonValue,
    ModelDumpable,
    RawProcessInput,
    is_json_array,
    is_json_object,
    is_model_dumpable,
    safe_int,
)
from core.schemas.process_graph import (
    CodeBlock,
    Comment,
    Connection,
    EnvironmentType,
    GraphOrigin,
    NodePosition,
    PortSpec,
    ProcessGraph,
    TabFlow,
    TodoList,
    TodoTask,
    Unit,
)
from core.schemas.training_config import (
    CallbacksConfig,
    EnvironmentConfig,
    GoalConfig,
    HyperparametersConfig,
    RewardsConfig,
    RunConfig,
    TrainingConfig,
)
from units.registry import get_unit_spec

TODO_TASK_DEADLINE = 320  # default deadline (will be converted to str)

# ---- main process graph normalizer ---

def to_process_graph(
    raw: RawProcessInput,
    format: FormatProcess = "dict",
) -> ProcessGraph:
    """
    Normalize raw input to the canonical ProcessGraph.

    Args:
        raw: Canonical JSON object, JSON array, YAML string, or format-specific
            JSON string.
        format: Input format.

    Returns:
        Validated canonical ProcessGraph.

    Raises:
        ValueError: If raw is invalid or missing required fields.
        pydantic.ValidationError: If schema validation fails.
    """
    # ----------- External converters to ProcessGraph ---------

    if format == "yaml":
        if not isinstance(raw, str):
            raise ValueError("raw for format='yaml' must be a YAML string")

        loaded: object = yaml.safe_load(raw) or {}

        if not is_json_object(loaded):
            raise ValueError(
                "raw for format='yaml' must contain a JSON object"
            )

        data = loaded

    elif format == "dict":
        if not is_json_object(raw):
            raise ValueError(
                "raw for format='dict' must be a JSON object"
            )

        data: JsonObject = dict(raw)

        raw_comments_value: object = data.get("comments")
        raw_comments: JsonArray = []

        if is_json_array(raw_comments_value):
            raw_comments = raw_comments_value

        has_system_comment = any(
            is_json_object(item)
            and item.get("id") == "comment_system_canonical"
            for item in raw_comments
        )

        if not has_system_comment:
            canonical_comments: JsonArray = [
                make_canonical_system_comment(),
                *raw_comments,
            ]
            data["comments"] = canonical_comments

    elif format == "node_red":
        source = require_json_document(raw, format=format)
        data = _node_red_to_canonical_dict(source)

    elif format == "template":
        source = require_json_object(
            require_json_document(raw, format=format),
            format=format,
        )
        data = _template_to_canonical_dict(source)

    elif format == "pyflow":
        source = require_json_object(
            require_json_document(raw, format=format),
            format=format,
        )
        data = _pyflow_to_canonical_dict(source)

    elif format == "ryven":
        source = require_json_object(
            require_json_document(raw, format=format),
            format=format,
        )
        data = _ryven_to_canonical_dict(source)

    elif format == "idaes":
        source = require_json_object(
            require_json_document(raw, format=format),
            format=format,
        )
        data = _idaes_to_canonical_dict(source)

    elif format == "n8n":
        source = require_json_object(
            require_json_document(raw, format=format),
            format=format,
        )
        data = _n8n_to_canonical_dict(source)

    elif format == "comfyui":
        source = require_json_object(
            require_json_document(raw, format=format),
            format=format,
        )
        data = _comfyui_to_canonical_dict(source)

    # Parse keep_alive
    keep_alive = parse_keep_alive(data.get("keep_alive", False))

    # Ensure all unit modules are registered so inference can use UnitSpec.environment_tags (type-agnostic).
    ensure_env_agnostic_units_registered()
    try:
        from units.env_loaders import ensure_all_environment_units_registered

        ensure_all_environment_units_registered()
    except (ImportError, AttributeError):
        pass
    # Re-apply canonical so Aggregate, Switch, etc. keep canonical port counts (e.g. n8n Merge has 2 ports; we use Aggregate for agent flow).
    try:
        from units.canonical import register_canonical_units

        register_canonical_units()
    except (ImportError, AttributeError):
        pass

    # Collect all unit types from top-level and tabs (canonicalized)
    # to infer environments.
    all_unit_types: list[str] = []

    units_raw = data.get("units")

    if isinstance(units_raw, list):
        for unit_raw in units_raw:
            if (
                isinstance(unit_raw, dict)
                and unit_raw.get("type") is not None
            ):
                all_unit_types.append(
                    canonical_unit_type(str(unit_raw["type"]))
                )

    tabs_raw = data.get("tabs")

    if isinstance(tabs_raw, list):
        for tab_raw in tabs_raw:
            if not isinstance(tab_raw, dict):
                continue

            tab_units_raw = tab_raw.get("units")

            if not isinstance(tab_units_raw, list):
                continue

            for unit_raw in tab_units_raw:
                if (
                    isinstance(unit_raw, dict)
                    and unit_raw.get("type") is not None
                ):
                    all_unit_types.append(
                        canonical_unit_type(str(unit_raw["type"]))
                    )

    # Infer environment tags from unit types via registry (type-agnostic).
    detected = infer_environments_from_unit_types(all_unit_types)
    environments_list: list[str] | None = detected if detected else None
    if "thermodynamic" in detected:
        env_type = EnvironmentType.THERMODYNAMIC
    elif "data_bi" in detected:
        env_type = EnvironmentType.DATA_BI
    elif "web" in detected:
        env_type = EnvironmentType.WEB
    elif "messengers" in detected:
        env_type = EnvironmentType.MESSENGERS
    elif "time" in detected:
        env_type = EnvironmentType.TIME
    elif "network" in detected:
        env_type = EnvironmentType.NETWORK
    elif "discovery" in detected:
        env_type = EnvironmentType.DISCOVERY
    elif "semantics" in detected:
        env_type = EnvironmentType.SEMANTICS
    elif "rag" in detected:
        env_type = EnvironmentType.RAG
    elif "coding" in detected:
        env_type = EnvironmentType.CODING
    elif "taskvector" in detected:
        env_type = EnvironmentType.TASKVECTOR
    elif "office" in detected:
        env_type = EnvironmentType.OFFICE
    else:
        # No runtime env detected from units: use explicit from input only if set; otherwise leave unspecified.
        explicit = data.get("environment_type") or data.get("process_environment_type")
        if isinstance(explicit, str) and explicit.strip():
            try:
                env_type = EnvironmentType(explicit.lower().strip())
            except ValueError:
                env_type = EnvironmentType.UNSPECIFIED
        else:
            env_type = EnvironmentType.UNSPECIFIED

    # Normalize units: list of dicts with id, type, optional controllable,
    # optional params.
    #
    # Unit types are canonicalized
    # (e.g. rl_agent -> RLAgent; llm_agent -> LLMAgent).
    #
    # The registry was already ensured above for inference; ensure the primary
    # environment is also registered for any late lookups.
    ensure_environment_units_registered(env_type)
    ensure_environments_units_registered(detected)

    units: list[Unit] = []

    units_raw_value: object = data.get("units", [])
    units_raw_list: JsonArray = (
        units_raw_value if is_json_array(units_raw_value) else []
    )


    for unit_raw in units_raw_list:
        if isinstance(unit_raw, dict):
            unit_type_value = unit_raw.get("type")

            if unit_type_value is None:
                raise ValueError("Each unit must contain a 'type' field")

            unit_id_value = unit_raw.get("id")

            if unit_id_value is None:
                raise ValueError("Each unit must contain an 'id' field")

            name_value = unit_raw.get("name")
            name = (
                name_value.strip()
                if isinstance(name_value, str) and name_value.strip()
                else None
            )

            input_ports = parse_port_specs(unit_raw.get("input_ports"))
            output_ports = parse_port_specs(unit_raw.get("output_ports"))

            canonical_type = canonical_unit_type(str(unit_type_value))

            if not input_ports and not output_ports:
                spec = get_unit_spec(canonical_type)

                if spec:
                    input_ports = [
                        PortSpec(name=port_name, type=port_type or None)
                        for port_name, port_type in spec.input_ports
                    ]
                    output_ports = [
                        PortSpec(name=port_name, type=port_type or None)
                        for port_name, port_type in spec.output_ports
                    ]

            params_value = unit_raw.get("params", {})
            params: dict[str, object] = (
                dict(params_value)
                if isinstance(params_value, dict)
                else {}
            )

            units.append(
                Unit(
                    id=str(unit_id_value),
                    type=canonical_type,
                    controllable=bool(
                        unit_raw.get("controllable", True)
                    ),
                    params=params,
                    name=name,
                    input_ports=input_ports,
                    output_ports=output_ports,
                )
            )

        else:
            unit = Unit.model_validate(unit_raw)
            units.append(
                unit.model_copy(
                    update={
                        "type": canonical_unit_type(unit.type),
                    }
                )
            )

    # Normalize connections: list of {from, to}
    conn_raw = data.get("connections", [])
    connections_list = ensure_list_connections(conn_raw)
    connections = [Connection.model_validate(c) for c in connections_list]

    # Optional code_blocks (language-agnostic: id, language, source)
    code_blocks_raw = data.get("code_blocks", [])
    code_blocks = (
        [CodeBlock.model_validate(b) for b in code_blocks_raw]
        if isinstance(code_blocks_raw, list)
        else []
    )

    # Optional layout (per-unit x, y from Node-RED / n8n / dict)
    layout_raw = data.get("layout")
    layout: dict[str, NodePosition] | None = None

    if isinstance(layout_raw, dict) and layout_raw:
        parsed_layout: dict[str, NodePosition] = {}

        for uid, pos in layout_raw.items():
            if not isinstance(pos, dict):
                continue

            layout_x_raw = pos.get("x")
            layout_y_raw = pos.get("y")

            layout_x: float | None = (
                float(layout_x_raw)
                if isinstance(layout_x_raw, (int, float))
                and not isinstance(layout_x_raw, bool)
                else None
            )
            layout_y: float | None = (
                float(layout_y_raw)
                if isinstance(layout_y_raw, (int, float))
                and not isinstance(layout_y_raw, bool)
                else None
            )

            if layout_x is None or layout_y is None:
                continue

            parsed_layout[str(uid)] = NodePosition(
                x=layout_x,
                y=layout_y,
            )

        layout = parsed_layout or None

    # Optional origin metadata (e.g., Node-RED tabs). Default to canonical when never imported or imported as canonical.
    origin_raw = data.get("origin")
    origin: GraphOrigin | None = None
    if isinstance(origin_raw, dict) and origin_raw:
        try:
            origin = GraphOrigin.model_validate(origin_raw)
        except (TypeError, ValueError):
            origin = GraphOrigin(canonical=True)
    else:
        origin = GraphOrigin(canonical=True)

    # origin_format: for export validation (export only to same runtime format)
    origin_format = data.get("origin_format")
    if origin_format is None and format in (
        "node_red",
        "pyflow",
        "n8n",
        "ryven",
        "dict",
    ):
        origin_format = format

    # Optional tabs (multi-tab flows, e.g. Node-RED).
    # ProcessGraph requires top-level units/connections to mirror the first tab.
    tabs_raw = data.get("tabs")
    tabs_list_pg: list[TabFlow] | None = None

    if isinstance(tabs_raw, list) and tabs_raw:
        parsed_tabs: list[TabFlow] = []

        for tab_raw in tabs_raw:
            if not isinstance(tab_raw, dict):
                continue

            tab_id = str(tab_raw.get("id", "")).strip()
            if not tab_id:
                continue

            tab_units: list[Unit] = []

            units_raw = tab_raw.get("units", [])
            if not isinstance(units_raw, list):
                units_raw = []

            for unit_raw in units_raw:
                if not isinstance(unit_raw, dict):
                    continue

                unit_id = str(unit_raw.get("id", "")).strip()
                unit_type_raw = unit_raw.get("type")

                if not unit_id or unit_type_raw is None:
                    continue

                unit_type = canonical_unit_type(str(unit_type_raw))

                name_raw = unit_raw.get("name")
                name = (
                    name_raw.strip()
                    if isinstance(name_raw, str) and name_raw.strip()
                    else None
                )

                params_raw = unit_raw.get("params", {})

                unit_params: dict[str, object] = {}
                if isinstance(params_raw, dict):
                    for key, value in params_raw.items():
                        unit_params[str(key)] = value

                input_ports = parse_port_specs(unit_raw.get("input_ports"))
                output_ports = parse_port_specs(unit_raw.get("output_ports"))

                if not input_ports and not output_ports:
                    spec = get_unit_spec(unit_type)
                    if spec is not None:
                        input_ports = [
                            PortSpec(name=port_name, type=port_type or None)
                            for port_name, port_type in spec.input_ports
                        ]
                        output_ports = [
                            PortSpec(name=port_name, type=port_type or None)
                            for port_name, port_type in spec.output_ports
                        ]

                tab_units.append(
                    Unit(
                        id=unit_id,
                        type=unit_type,
                        controllable=bool(unit_raw.get("controllable", False)),
                        params=unit_params,
                        name=name,
                        input_ports=input_ports,
                        output_ports=output_ports,
                    )
                )

            connections_raw = tab_raw.get("connections", [])
            tab_connections = [
                Connection.model_validate(connection)
                for connection in ensure_list_connections(connections_raw)
            ]

            label_raw = tab_raw.get("label")
            tab_label: str | None = (
                label_raw if isinstance(label_raw, str) else None
            )

            disabled_raw = tab_raw.get("disabled")
            tab_disabled: bool | None = (
                disabled_raw if isinstance(disabled_raw, bool) else None
            )

            parsed_tabs.append(
                TabFlow(
                    id=tab_id,
                    label=tab_label,
                    disabled=tab_disabled,
                    units=tab_units,
                    connections=tab_connections,
                )
            )

        if parsed_tabs:
            tabs_list_pg = parsed_tabs

            # Required backward-compatibility mirror:
            # top-level graph structure equals the first tab.
            units = parsed_tabs[0].units
            connections = parsed_tabs[0].connections


    metadata = data.get("metadata")
    if isinstance(metadata, dict) and metadata:
        metadata = dict(metadata)
    else:
        metadata = None

    comments_raw = data.get("comments", [])
    comments: list[Comment] | None = None

    if isinstance(comments_raw, list) and comments_raw:
        parsed_comments: list[Comment] = []

        for comment_raw in comments_raw:
            if not isinstance(comment_raw, dict):
                continue

            comment_id = comment_raw.get("id")
            comment_info = comment_raw.get("info")

            if comment_id is None or comment_info is None:
                continue

            x_raw = comment_raw.get("x")
            y_raw = comment_raw.get("y")

            x_value: float | None = (
                float(x_raw)
                if isinstance(x_raw, (int, float)) and not isinstance(x_raw, bool)
                else None
            )
            y_value: float | None = (
                float(y_raw)
                if isinstance(y_raw, (int, float)) and not isinstance(y_raw, bool)
                else None
            )

            parsed_comments.append(
                Comment(
                    id=str(comment_id),
                    info=str(comment_info),
                    commenter=str(comment_raw.get("commenter") or ""),
                    created_at=str(comment_raw.get("created_at", "")),
                    x=x_value,
                    y=y_value,
                )
            )

        comments = parsed_comments or None

    todo_lists: list[TodoList] = []
    todo_raws = data.get("todo_lists")

    if isinstance(todo_raws, list):
        for todo_raw in todo_raws:
            if not isinstance(todo_raw, dict):
                continue

            tasks_list: list[TodoTask] = []
            tasks_raw = todo_raw.get("tasks")

            if isinstance(tasks_raw, list):
                for t in tasks_raw:
                    if isinstance(t, dict) and t.get("id") is not None and t.get("text") is not None:
                        deadline_raw = t.get("deadline")

                        # Default when missing/None/empty (keep type as str | None)
                        if deadline_raw in (None, ""):
                            deadline: str | None = str(TODO_TASK_DEADLINE)
                        else:
                            deadline = str(deadline_raw).strip()

                        tasks_list.append(
                            TodoTask(
                                id=str(t["id"]),
                                text=str(t["text"]),
                                completed=bool(t.get("completed", False)),
                                created_at=str(t.get("created_at", "")),
                                implementer=(str(t["implementer"]).strip() if t.get("implementer") not in (None, "") else None),
                                curator=(str(t["curator"]).strip() if t.get("curator") not in (None, "") else None),
                                finished_at=(str(t["finished_at"]).strip() if t.get("finished_at") not in (None, "") else None),
                                deadline=deadline,
                            )
                        )

            _title = todo_raw.get("title")
            title = (str(_title).strip() or None) if _title is not None else None

            todo_x_raw = todo_raw.get("x")
            todo_y_raw = todo_raw.get("y")

            todo_x: float | None = (
                float(todo_x_raw)
                if isinstance(todo_x_raw, (int, float))
                and not isinstance(todo_x_raw, bool)
                else None
            )

            todo_y: float | None = (
                float(todo_y_raw)
                if isinstance(todo_y_raw, (int, float))
                and not isinstance(todo_y_raw, bool)
                else None
            )

            todo_lists.append(
                TodoList(
                    id=str(todo_raw.get("id", "todo_list_default")),
                    title=title,
                    tasks=tasks_list,
                    x=todo_x,
                    y=todo_y,
                )
            )

    # Normalize origin_format for ProcessGraph.
    origin_format_raw = data.get("origin_format")
    normalized_origin_format: str | None = (
        origin_format_raw
        if isinstance(origin_format_raw, str)
        else None
    )

    # Normalize metadata for ProcessGraph.
    metadata_raw = data.get("metadata")
    normalized_metadata: dict[str, object] | None = None

    if isinstance(metadata_raw, dict):
        normalized_metadata = {
            str(key): value
            for key, value in metadata_raw.items()
        }

    # Set runtime on import so agents/chat can read it for conditional prompts
    # (native vs external).
    origin_payload: dict[str, JsonValue] = cast(
        dict[str, JsonValue],
        origin.model_dump(mode="json"),
    )

    runtime_input: dict[str, JsonValue] = {
        "origin_format": normalized_origin_format,
        "origin": origin_payload,
    }

    runtime: Literal["native", "external"] = (
        "native"
        if is_canonical_runtime(runtime_input)
        else "external"
    )

    return ProcessGraph(
        environment_type=env_type,
        environments=environments_list,
        keep_alive=keep_alive,
        units=units,
        connections=connections,
        code_blocks=code_blocks,
        layout=layout,
        origin=origin,
        origin_format=normalized_origin_format,
        runtime=runtime,
        tabs=tabs_list_pg,
        metadata=normalized_metadata,
        comments=comments,
        todo_lists=todo_lists,
    )

# ---- training config normalizer ---
def to_training_config(
    raw: JsonObject | str,
    format: FormatTraining = "dict",
) -> TrainingConfig:
    """
    Normalize raw input to canonical TrainingConfig.

    Args:
        raw: A JSON-compatible mapping or YAML string.
        format: ``"dict"`` for mappings or ``"yaml"`` for YAML strings.

    Returns:
        Validated canonical TrainingConfig.

    Raises:
        ValueError: If the input format or structure is invalid.
        pydantic.ValidationError: If schema validation fails.
    """
    format_value = str(format)

    if format_value == "yaml":
        if not isinstance(raw, str):
            raise ValueError(
                "raw must be a YAML string when format='yaml'"
            )

        data = load_yaml_object(raw)

    elif format_value == "dict":
        if not is_json_object(raw):
            raise ValueError(
                "raw must be a JSON object when format='dict'"
            )

        data = raw

    else:
        raise ValueError(
            f"Unsupported training config format: {format_value!r}"
        )

    goal = GoalConfig.model_validate(
        as_object(data.get("goal"), "goal")
    )

    rewards = RewardsConfig.model_validate(
        as_object(data.get("rewards"), "rewards")
    )

    hyperparameters = HyperparametersConfig.model_validate(
        as_object(
            data.get("hyperparameters"),
            "hyperparameters",
        )
    )

    callbacks_raw = as_object(
        data.get("callbacks"),
        "callbacks",
    )

    model_dir_value = callbacks_raw.get("model_dir")

    if isinstance(model_dir_value, str) and model_dir_value:
        base = model_dir_value.rstrip("/")

        name_prefix_value = callbacks_raw.get(
            "name_prefix",
            "ppo_temp_control",
        )

        name_prefix = (
            name_prefix_value
            if isinstance(name_prefix_value, str)
            else "ppo_temp_control"
        )

        callbacks_data: JsonObject = {
            **callbacks_raw,
            "model_dir": base,
            "name_prefix": name_prefix,
            "save_path": f"{base}/checkpoints/",
            "best_model_save_path": f"{base}/best/",
            "log_path": f"{base}/logs/eval/",
            "tensorboard_log": f"{base}/logs/tensorboard/",
            "final_model_save_path": f"{base}/{name_prefix}_final",
        }
    else:
        callbacks_data = callbacks_raw

    callbacks = CallbacksConfig.model_validate(callbacks_data)

    run = RunConfig.model_validate(
        as_object(data.get("run"), "run")
    )

    environment_raw = as_object(
        data.get("environment"),
        "environment",
    )

    # Preserve legacy aliases:
    #   config -> adapter_config
    #   kwargs -> env_kwargs
    environment_data: JsonObject = dict(environment_raw)

    if "adapter_config" not in environment_data:
        adapter_config = environment_data.get("config")

        if is_json_object(adapter_config):
            environment_data["adapter_config"] = adapter_config

    if "env_kwargs" not in environment_data:
        env_kwargs = environment_data.get("kwargs")

        if is_json_object(env_kwargs):
            environment_data["env_kwargs"] = env_kwargs

    environment = EnvironmentConfig.model_validate(environment_data)

    algorithm_value = data.get("algorithm", "PPO")
    algorithm = (
        algorithm_value
        if isinstance(algorithm_value, str)
        else "PPO"
    )

    total_timesteps_value = data.get(
        "total_timesteps",
        100_000,
    )

    total_timesteps = safe_int(total_timesteps_value)

    if total_timesteps is None:
        raise ValueError(
            "total_timesteps must be an integer"
        )

    return TrainingConfig(
        environment=environment,
        goal=goal,
        rewards=rewards,
        algorithm=algorithm,
        hyperparameters=hyperparameters,
        total_timesteps=total_timesteps,
        run=run,
        callbacks=callbacks,
    )

# ---- additionlal normalization functions ---

def load_process_graph_from_file(
    path: str | Path,
    format: FormatProcess | None = None,
) -> ProcessGraph:
    """
    Load and normalize a process graph from a file.

    If ``format`` is omitted:

    - ``.yaml`` and ``.yml`` are treated as YAML.
    - ``.json`` is treated as canonical dict format.

    An explicit format may be one of:

    ``yaml``, ``dict``, ``node_red``, ``template``, ``pyflow``,
    ``ryven``, ``idaes``, ``n8n``, or ``comfyui``.
    """
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Process config file not found: {file_path}"
        )

    text = file_path.read_text(encoding="utf-8")

    selected_format: FormatProcess

    if format is None:
        suffix = file_path.suffix.lower()

        if suffix in {".yaml", ".yml"}:
            selected_format = "yaml"
        elif suffix == ".json":
            selected_format = "dict"
        else:
            raise ValueError(
                "Cannot infer process graph format from suffix "
                + f"{suffix!r}; specify format explicitly"
            )
    else:
        selected_format = format

    if selected_format == "dict":
        loaded = cast(object, json.loads(text))

        if not is_json_object(loaded):
            raise ValueError(
                "JSON process graph must contain an object at the root"
            )

        return to_process_graph(
            loaded,
            format="dict",
        )

    return to_process_graph(
        text,
        format=selected_format,
    )


def load_training_config_from_file(path: str | Path) -> TrainingConfig:
    """Load and normalize training config from a YAML file. Use everywhere for consistency."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Training config file not found: {path}")
    text = path.read_text()
    return to_training_config(text, format="yaml")


def get_process_graph_from_any(value: object | None) -> ProcessGraph:
    from core.normalizer import to_process_graph

    if value is None:
        raise TypeError("graph missing")

    if isinstance(value, ProcessGraph):
        return value

    if is_json_object(value):
        return to_process_graph(value, format="dict")

    if is_model_dumpable(value):
        dumped = value.model_dump(by_alias=True)
        json_dumped = to_json_value(dumped)

        if not isinstance(json_dumped, dict):
            raise TypeError(
                "model-dumpable graph input must produce a JSON object"
            )

        return to_process_graph(json_dumped, format="dict")

    raise TypeError(
        "graph input must be a dict, ProcessGraph, or model-dumpable object"
    )


def graph_to_json_object(value: object) -> JsonObject:
    """Convert a graph value into a JSON-compatible graph object."""
    default_graph: JsonObject = {
        "units": [],
        "connections": [],
    }

    if value is None:
        return default_graph

    if is_json_object(value):
        return value

    if isinstance(value, ModelDumpable):
        dumped = value.model_dump(by_alias=True)

        if is_json_object(dumped):
            return dumped

    return default_graph


def as_process_graph(value: object) -> ProcessGraph:
    if isinstance(value, ProcessGraph):
        return value

    if isinstance(value, Mapping):
        return ProcessGraph.model_validate(value)

    raise TypeError(f"Expected ProcessGraph or mapping, got {type(value).__name__}")
