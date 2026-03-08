"""
Data normalizer: map raw input (dict, YAML, Node-RED) to canonical ProcessGraph and TrainingConfig.
All external formats flow through here so the rest of the stack sees one schema.

Unit types and the controllable flag are taken from the unit spec (units/registry.py).
For correct controllable detection when importing flows, ensure unit modules are registered
(e.g. at app startup: units.thermodynamic, units.agents, units.pipelines).
"""
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import ValidationError

from schemas.process_graph import (
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
from schemas.training_config import (
    EnvironmentConfig,
    TrainingConfig,
    GoalConfig,
    RewardsConfig,
    HyperparametersConfig,
    CallbacksConfig,
    RunConfig,
)
from normalizer.comfyui_import import to_canonical_dict as _comfyui_to_canonical_dict
from normalizer.idaes_import import to_canonical_dict as _idaes_to_canonical_dict
from normalizer.n8n_import import to_canonical_dict as _n8n_to_canonical_dict
from normalizer.node_red_import import to_canonical_dict as _node_red_to_canonical_dict
from normalizer.pyflow_import import to_canonical_dict as _pyflow_to_canonical_dict
from normalizer.ryven_import import to_canonical_dict as _ryven_to_canonical_dict
from normalizer.shared import _canonical_unit_type, _ensure_list_connections, infer_environments_from_unit_types
from normalizer.template_import import to_canonical_dict as _template_to_canonical_dict
from units.registry import get_unit_spec


def _ensure_env_agnostic_units_registered() -> None:
    """Ensure RLAgent, LLMAgent, canonical units, etc. are in the registry so get_unit_spec works for all graph unit types."""
    try:
        from units.register_env_agnostic import register_env_agnostic_units
        register_env_agnostic_units()
    except Exception:
        pass


def _ensure_environment_units_registered(env_type: Any) -> None:
    """Ensure environment-specific units are in the registry (via units.env_loaders)."""
    from units.env_loaders import ensure_environment_units_registered

    val = getattr(env_type, "value", env_type) if env_type is not None else "thermodynamic"
    if isinstance(val, str):
        val = val.lower().strip()
    ensure_environment_units_registered(val)


def _ensure_environments_units_registered(environments: list[str]) -> None:
    """Register unit modules for every runtime environment in the list (from env_loaders registry)."""
    from units.env_loaders import ensure_environment_units_registered

    for tag in environments:
        ensure_environment_units_registered(str(tag).strip().lower())


FormatProcess = Literal["yaml", "dict", "node_red", "template", "pyflow", "ryven", "idaes", "n8n", "comfyui"]
FormatTraining = Literal["yaml", "dict"]


def _parse_port_specs(raw: Any) -> list[PortSpec]:
    """Parse input_ports/output_ports from canonical dict (list of {name, type?}). Returns [] when missing or empty."""
    if not isinstance(raw, list) or not raw:
        return []
    out: list[PortSpec] = []
    for item in raw:
        if isinstance(item, dict) and item.get("name") is not None:
            out.append(PortSpec(name=str(item["name"]), type=str(item["type"]) if item.get("type") is not None else None))
        else:
            try:
                out.append(PortSpec.model_validate(item))
            except Exception:
                pass
    return out


def to_process_graph(raw: dict[str, Any] | str | list[Any], format: FormatProcess = "dict") -> ProcessGraph:
    """
    Normalize raw input to canonical ProcessGraph.
    Use everywhere process data is loaded so consistency is guaranteed.

    Args:
        raw: Dict (canonical shape), YAML string, or flow (dict/list/JSON str) per format.
        format: "dict" | "yaml" | "node_red" | "template" | "pyflow" | "ryven" | "idaes".

    Returns:
        Validated canonical ProcessGraph.

    Raises:
        ValueError: If raw is invalid or missing required fields.
        pydantic.ValidationError: If schema validation fails.
    """
    if format == "yaml" and isinstance(raw, str):
        data: dict[str, Any] = yaml.safe_load(raw) or {}
    elif format == "dict" and isinstance(raw, dict):
        data = raw
    elif format == "node_red":
        if isinstance(raw, str):
            raw = json.loads(raw)
        data = _node_red_to_canonical_dict(raw)
    elif format == "template":
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            raise ValueError("raw for format='template' must be dict or JSON str")
        data = _template_to_canonical_dict(raw)
    elif format == "pyflow":
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            raise ValueError("raw for format='pyflow' must be dict or JSON str")
        data = _pyflow_to_canonical_dict(raw)
    elif format == "ryven":
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            raise ValueError("raw for format='ryven' must be dict or JSON str")
        data = _ryven_to_canonical_dict(raw)
    elif format == "idaes":
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            raise ValueError("raw for format='idaes' must be dict or JSON str")
        data = _idaes_to_canonical_dict(raw)
    elif format == "n8n":
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            raise ValueError("raw for format='n8n' must be dict or JSON str")
        data = _n8n_to_canonical_dict(raw)
    elif format == "comfyui":
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            raise ValueError("raw for format='comfyui' must be dict or JSON str")
        data = _comfyui_to_canonical_dict(raw)
    else:
        raise ValueError(
            "format must be 'dict', 'yaml', 'node_red', 'template', 'pyflow', 'ryven', 'idaes', 'n8n', or 'comfyui'"
        )

    # Ensure all unit modules are registered so inference can use UnitSpec.environment_tags (type-agnostic).
    _ensure_env_agnostic_units_registered()
    try:
        from units.env_loaders import ensure_all_environment_units_registered

        ensure_all_environment_units_registered()
    except Exception:
        pass

    # Collect all unit types from top-level and tabs (canonicalized) to infer environments.
    units_raw = data.get("units", [])
    all_unit_types: list[str] = []
    for u in units_raw:
        if isinstance(u, dict) and u.get("type") is not None:
            all_unit_types.append(_canonical_unit_type(str(u["type"])))
    tabs_raw = data.get("tabs")
    if isinstance(tabs_raw, list):
        for t in tabs_raw:
            if isinstance(t, dict):
                for u in t.get("units") or []:
                    if isinstance(u, dict) and u.get("type") is not None:
                        all_unit_types.append(_canonical_unit_type(str(u["type"])))

    # Infer environment tags from unit types via registry (type-agnostic).
    detected = infer_environments_from_unit_types(all_unit_types)
    environments_list: list[str] | None = detected if detected else None
    if "thermodynamic" in detected:
        env_type = EnvironmentType.THERMODYNAMIC
    elif "data_bi" in detected:
        env_type = EnvironmentType.DATA_BI
    else:
        # No runtime env detected: keep explicit from input or default thermodynamic.
        env_type = data.get("environment_type", "thermodynamic")
        if isinstance(env_type, str):
            env_type = EnvironmentType(env_type.lower().strip())

    # Normalize units: list of dicts with id, type, optional controllable, optional params
    # Unit types are canonicalized (e.g. rl_agent -> RLAgent; llm_agent -> LLMAgent).
    # Registry already ensured above for inference; ensure primary env for any late lookups.
    _ensure_environment_units_registered(env_type)
    _ensure_environments_units_registered(detected)
    units: list[Unit] = []
    for u in units_raw:
        if isinstance(u, dict):
            name_val = u.get("name")
            name = str(name_val).strip() if isinstance(name_val, str) and name_val.strip() else None
            in_ports = _parse_port_specs(u.get("input_ports"))
            out_ports = _parse_port_specs(u.get("output_ports"))
            if not in_ports and not out_ports:
                spec = get_unit_spec(_canonical_unit_type(str(u["type"])))
                if spec:
                    in_ports = [PortSpec(name=n, type=t or None) for n, t in spec.input_ports]
                    out_ports = [PortSpec(name=n, type=t or None) for n, t in spec.output_ports]
            units.append(
                Unit(
                    id=str(u["id"]),
                    type=_canonical_unit_type(str(u["type"])),
                    controllable=bool(u.get("controllable", True)),
                    params=dict(u.get("params", {})),
                    name=name,
                    input_ports=in_ports,
                    output_ports=out_ports,
                )
            )
        else:
            unit = Unit.model_validate(u)
            units.append(unit.model_copy(update={"type": _canonical_unit_type(unit.type)}))

    # Normalize connections: list of {from, to}
    conn_raw = data.get("connections", [])
    connections_list = _ensure_list_connections(conn_raw)
    connections = [Connection.model_validate(c) for c in connections_list]

    # Optional code_blocks (language-agnostic: id, language, source)
    code_blocks_raw = data.get("code_blocks", [])
    code_blocks = [CodeBlock.model_validate(b) for b in code_blocks_raw] if isinstance(code_blocks_raw, list) else []

    # Optional layout (per-unit x, y from Node-RED / n8n / dict)
    layout_raw = data.get("layout")
    layout: dict[str, NodePosition] | None = None
    if isinstance(layout_raw, dict) and layout_raw:
        layout = {}
        for uid, pos in layout_raw.items():
            if isinstance(pos, dict) and "x" in pos and "y" in pos:
                try:
                    layout[str(uid)] = NodePosition(x=float(pos["x"]), y=float(pos["y"]))
                except (TypeError, ValueError):
                    pass
        layout = layout if layout else None

    # Optional origin metadata (e.g., Node-RED tabs). Default to canonical when never imported or imported as canonical.
    origin_raw = data.get("origin")
    origin: GraphOrigin | None = None
    if isinstance(origin_raw, dict) and origin_raw:
        try:
            origin = GraphOrigin.model_validate(origin_raw)
        except Exception:
            origin = GraphOrigin(canonical=True)
    else:
        origin = GraphOrigin(canonical=True)

    # origin_format: for export validation (export only to same runtime format)
    origin_format = data.get("origin_format")
    if origin_format is None and format in ("node_red", "pyflow", "n8n", "ryven", "dict"):
        origin_format = format

    # Optional tabs (multi-tab flows, e.g. Node-RED). When present, top-level units/connections are first tab.
    tabs_raw = data.get("tabs")
    tabs_list_pg: list[TabFlow] | None = None
    if isinstance(tabs_raw, list) and tabs_raw:
        tabs_list_pg = []
        for t in tabs_raw:
            if not isinstance(t, dict):
                continue
            tab_id = str(t.get("id", ""))
            if not tab_id:
                continue
            tab_units: list[Unit] = []
            for u in t.get("units") or []:
                if isinstance(u, dict):
                    name_val = u.get("name")
                    name = str(name_val).strip() if isinstance(name_val, str) and name_val.strip() else None
                    in_ports = _parse_port_specs(u.get("input_ports"))
                    out_ports = _parse_port_specs(u.get("output_ports"))
                    if not in_ports and not out_ports:
                        spec = get_unit_spec(_canonical_unit_type(str(u["type"])))
                        if spec:
                            in_ports = [PortSpec(name=n, type=t or None) for n, t in spec.input_ports]
                            out_ports = [PortSpec(name=n, type=t or None) for n, t in spec.output_ports]
                    tab_units.append(
                        Unit(
                            id=str(u["id"]),
                            type=_canonical_unit_type(str(u["type"])),
                            controllable=bool(u.get("controllable", True)),
                            params=dict(u.get("params", {})),
                            name=name,
                            input_ports=in_ports,
                            output_ports=out_ports,
                        )
                    )
                else:
                    unit = Unit.model_validate(u)
                    tab_units.append(unit.model_copy(update={"type": _canonical_unit_type(unit.type)}))
            conn_raw = t.get("connections") or []
            conn_list = _ensure_list_connections(conn_raw)
            tab_connections = [Connection.model_validate(c) for c in conn_list]
            tabs_list_pg.append(
                TabFlow(
                    id=tab_id,
                    label=t.get("label"),
                    disabled=t.get("disabled"),
                    units=tab_units,
                    connections=tab_connections,
                )
            )
        tabs_list_pg = tabs_list_pg if tabs_list_pg else None

    metadata = data.get("metadata")
    if isinstance(metadata, dict) and metadata:
        metadata = dict(metadata)
    else:
        metadata = None

    comments_raw = data.get("comments", [])
    comments: list[Comment] | None = None
    if isinstance(comments_raw, list) and comments_raw:
        comments = []
        for c in comments_raw:
            if isinstance(c, dict) and c.get("id") is not None and c.get("info") is not None:
                x_val, y_val = c.get("x"), c.get("y")
                comments.append(
                    Comment(
                        id=str(c["id"]),
                        info=str(c["info"]),
                        commenter=str(c.get("commenter") or ""),
                        created_at=str(c.get("created_at", "")),
                        x=float(x_val) if x_val is not None else None,
                        y=float(y_val) if y_val is not None else None,
                    )
                )
        comments = comments if comments else None

    todo_list_pg: TodoList | None = None
    todo_raw = data.get("todo_list")
    if isinstance(todo_raw, dict) and isinstance(todo_raw.get("tasks"), list):
        tasks_list: list[TodoTask] = []
        for t in todo_raw.get("tasks") or []:
            if isinstance(t, dict) and t.get("id") is not None and t.get("text") is not None:
                tasks_list.append(
                    TodoTask(
                        id=str(t["id"]),
                        text=str(t["text"]),
                        completed=bool(t.get("completed", False)),
                        created_at=str(t.get("created_at", "")),
                    )
                )
        _title = todo_raw.get("title")
        title = (str(_title).strip() or None) if _title is not None else None
        todo_list_pg = TodoList(
            id=str(todo_raw.get("id", "todo_list_default")),
            title=title,
            tasks=tasks_list,
        )

    return ProcessGraph(
        environment_type=env_type,
        environments=environments_list,
        units=units,
        connections=connections,
        code_blocks=code_blocks,
        layout=layout,
        origin=origin,
        origin_format=origin_format,
        tabs=tabs_list_pg,
        metadata=metadata,
        comments=comments,
        todo_list=todo_list_pg,
    )


def to_training_config(raw: dict[str, Any] | str, format: FormatTraining = "dict") -> TrainingConfig:
    """
    Normalize raw input to canonical TrainingConfig.
    Use everywhere training config is loaded so consistency is guaranteed.

    Args:
        raw: Either a dict (goal, rewards, algorithm, hyperparameters) or a YAML string.
        format: "dict" if raw is dict, "yaml" if raw is YAML string.

    Returns:
        Validated canonical TrainingConfig.

    Raises:
        ValueError: If raw is invalid.
        pydantic.ValidationError: If schema validation fails.
    """
    if format == "yaml" and isinstance(raw, str):
        data: dict[str, Any] = yaml.safe_load(raw) or {}
    elif format == "dict" and isinstance(raw, dict):
        data = raw
    else:
        raise ValueError("raw must be dict (format='dict') or YAML str (format='yaml')")

    goal_raw = data.get("goal", {})
    if isinstance(goal_raw, dict):
        goal = GoalConfig(
            type=str(goal_raw.get("type", "setpoint")),
            target_temp=goal_raw.get("target_temp"),
            target_volume_ratio=tuple(goal_raw["target_volume_ratio"]) if goal_raw.get("target_volume_ratio") else None,
            target_pressure_range=tuple(goal_raw["target_pressure_range"]) if goal_raw.get("target_pressure_range") else None,
        )
    else:
        goal = GoalConfig.model_validate(goal_raw)

    rewards_raw = data.get("rewards", {})
    if isinstance(rewards_raw, dict):
        rewards = RewardsConfig(
            preset=str(rewards_raw.get("preset", "temperature_and_volume")),
            weights=dict(rewards_raw.get("weights", {})),
        )
    else:
        rewards = RewardsConfig.model_validate(rewards_raw)

    hyper_raw = data.get("hyperparameters", {})
    if isinstance(hyper_raw, dict):
        hyperparameters = HyperparametersConfig(
            learning_rate=float(hyper_raw.get("learning_rate", 3e-4)),
            n_steps=int(hyper_raw.get("n_steps", 2048)),
            batch_size=int(hyper_raw.get("batch_size", 64)),
            n_epochs=int(hyper_raw.get("n_epochs", 10)),
            gamma=float(hyper_raw.get("gamma", 0.99)),
            gae_lambda=float(hyper_raw.get("gae_lambda", 0.95)),
            clip_range=float(hyper_raw.get("clip_range", 0.2)),
            ent_coef=float(hyper_raw.get("ent_coef", 0.01)),
        )
    else:
        hyperparameters = HyperparametersConfig.model_validate(hyper_raw)

    callbacks_raw = data.get("callbacks", {})
    if isinstance(callbacks_raw, dict):
        model_dir = callbacks_raw.get("model_dir")
        if model_dir:
            base = str(model_dir).rstrip("/")
            name_prefix = str(callbacks_raw.get("name_prefix", "ppo_temp_control"))
            callbacks = CallbacksConfig(
                eval_freq=int(callbacks_raw.get("eval_freq", 5000)),
                save_freq=int(callbacks_raw.get("save_freq", 10000)),
                model_dir=base,
                save_path=f"{base}/checkpoints/",
                name_prefix=name_prefix,
                best_model_save_path=f"{base}/best/",
                log_path=f"{base}/logs/eval/",
                tensorboard_log=f"{base}/logs/tensorboard/",
                final_model_save_path=f"{base}/{name_prefix}_final",
            )
        else:
            callbacks = CallbacksConfig(
                eval_freq=int(callbacks_raw.get("eval_freq", 5000)),
                save_freq=int(callbacks_raw.get("save_freq", 10000)),
                save_path=str(callbacks_raw.get("save_path", "./models/checkpoints/")),
                name_prefix=str(callbacks_raw.get("name_prefix", "ppo_temp_control")),
                best_model_save_path=str(callbacks_raw.get("best_model_save_path", "./models/best/")),
                log_path=str(callbacks_raw.get("log_path", "./logs/eval/")),
                tensorboard_log=str(callbacks_raw.get("tensorboard_log", "./logs/tensorboard/")),
                final_model_save_path=str(callbacks_raw.get("final_model_save_path", "./models/ppo_temperature_control_final")),
            )
    else:
        callbacks = CallbacksConfig.model_validate(callbacks_raw)

    run_raw = data.get("run", {})
    if isinstance(run_raw, dict):
        run = RunConfig(
            n_envs=int(run_raw.get("n_envs", 4)),
            randomize_params=bool(run_raw.get("randomize_params", True)),
            verbose=int(run_raw.get("verbose", 1)),
            test_episodes=int(run_raw.get("test_episodes", 5)),
        )
    else:
        run = RunConfig.model_validate(run_raw)

    total_timesteps = int(data.get("total_timesteps", 100000))

    env_raw = data.get("environment", {})
    if isinstance(env_raw, dict):
        environment = EnvironmentConfig(
            source=str(env_raw.get("source", "custom")),
            type=str(env_raw.get("type", "thermodynamic")),
            process_graph_path=env_raw.get("process_graph_path"),
            adapter=env_raw.get("adapter"),
            adapter_config=dict(env_raw.get("adapter_config") or env_raw.get("config") or {}),
            env_id=env_raw.get("env_id"),
            env_kwargs=dict(env_raw.get("env_kwargs") or env_raw.get("kwargs") or {}),
        )
    else:
        environment = EnvironmentConfig.model_validate(env_raw)

    return TrainingConfig(
        environment=environment,
        goal=goal,
        rewards=rewards,
        algorithm=str(data.get("algorithm", "PPO")),
        hyperparameters=hyperparameters,
        total_timesteps=total_timesteps,
        run=run,
        callbacks=callbacks,
    )


def load_process_graph_from_file(path: str | Path, format: FormatProcess | None = None) -> ProcessGraph:
    """Load and normalize process graph from a file. Use everywhere for consistency.
    format: None = infer from suffix (.yaml/.yml → yaml, .json → node_red), or explicit 'yaml'|'dict'|'node_red'|'template'|'pyflow'|'ryven'|'n8n'.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Process config file not found: {path}")
    text = path.read_text()
    if format is None:
        suffix = path.suffix.lower()
        format = "node_red" if suffix == ".json" else "yaml"
    if format == "dict":
        return to_process_graph(json.loads(text), format="dict")
    return to_process_graph(text, format=format)


def load_training_config_from_file(path: str | Path) -> TrainingConfig:
    """Load and normalize training config from a YAML file. Use everywhere for consistency."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Training config file not found: {path}")
    text = path.read_text()
    return to_training_config(text, format="yaml")
