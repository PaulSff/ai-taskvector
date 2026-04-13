"""
Dialog to add a node (unit) to the process graph.

Type list comes from the units_library workflow (UnitsLibrary unit), so the dialog
does not depend on core types. Supports all unit and pipeline types filtered by
runtime and environment for the current graph.
"""
from __future__ import annotations

from typing import Any, Callable

import flet as ft

from gui.components.workflow.units_library_types import get_units_library_type_lists

_DESC_MAX_LEN = 200
_ADD_ROW_ICON_SIZE = 22

# Internal bucket keys for grouped unit types (avoid clashing with env tag strings).
_GRP_TOPOLOGY = "__workflow_topology__"
_GRP_AGNOSTIC = "__core_agnostic__"
_GRP_OTHER = "__other__"
_GRP_PIPELINES = "__pipelines__"


def _display_group_title(key: str) -> str:
    if key == _GRP_TOPOLOGY:
        return "Workflow topology"
    if key == _GRP_AGNOSTIC:
        return "Core & environment-agnostic"
    if key == _GRP_OTHER:
        return "Other"
    if key == _GRP_PIPELINES:
        return "Pipelines"
    return str(key).replace("_", " ").title()


def _material_icon_data(name: str | None, *, fallback: str = "widgets") -> Any:
    """Map Material icon name string to ``ft.Icons`` (same rules as graph canvas nodes)."""
    raw = (name or fallback).strip() or fallback
    key = raw.upper().replace("-", "_").replace(" ", "_")
    return getattr(ft.Icons, key, getattr(ft.Icons, fallback.upper(), ft.Icons.WIDGETS))


def _leading_icon_for_add_row(type_name: str, *, is_pipeline: bool) -> ft.Icon:
    """Small leading icon: canvas node style for units, pipeline motif for pipeline types."""
    if is_pipeline:
        return ft.Icon(
            _material_icon_data("account_tree", fallback="account_tree"),
            size=_ADD_ROW_ICON_SIZE,
            color=ft.Colors.TEAL_300,
        )
    from gui.components.workflow.graph_style_config import get_default_style_config, get_node_style

    node_styles, _ = get_default_style_config()
    resolved = get_node_style(node_styles, type_name)
    icon_name = resolved.icon or "widgets"
    return ft.Icon(
        _material_icon_data(icon_name, fallback="widgets"),
        size=_ADD_ROW_ICON_SIZE,
        color=resolved.border_color,
    )


def _group_units_for_add_dialog(
    unit_entries: list[tuple[str, str]],
    graph_summary: dict[str, Any],
    get_unit_spec: Callable[[str], Any],
) -> list[tuple[str, list[tuple[str, str]]]]:
    """Split library unit rows into environment-ish groups (registry tags + graph environments)."""
    env_raw = graph_summary.get("environments") or []
    if isinstance(env_raw, list):
        graph_envs = sorted({str(e).strip().lower() for e in env_raw if e and str(e).strip()})
    else:
        graph_envs = []
    graph_env_set = set(graph_envs)

    buckets: dict[str, list[tuple[str, str]]] = {}

    def add_to(key: str, item: tuple[str, str]) -> None:
        buckets.setdefault(key, []).append(item)

    for item in unit_entries:
        name, _desc = item
        spec = get_unit_spec(name)
        if spec is None:
            add_to(_GRP_OTHER, item)
            continue
        tags = {str(t).strip().lower() for t in (spec.environment_tags or []) if t and str(t).strip()}
        agnostic = bool(getattr(spec, "environment_tags_are_agnostic", False))
        if agnostic or not tags:
            add_to(_GRP_AGNOSTIC, item)
            continue
        hit = sorted(tags & graph_env_set)
        if hit:
            add_to(hit[0], item)
            continue
        if "canonical" in tags or "rl training" in tags:
            add_to(_GRP_TOPOLOGY, item)
            continue
        add_to(_GRP_OTHER, item)

    out: list[tuple[str, list[tuple[str, str]]]] = []
    for e in graph_envs:
        if e in buckets and buckets[e]:
            out.append((e, buckets[e]))
    for key in (_GRP_TOPOLOGY, _GRP_AGNOSTIC, _GRP_OTHER):
        if key in buckets and buckets[key]:
            out.append((key, buckets[key]))
    return out


def _build_expansion_type_pickers(
    grouped_units: list[tuple[str, list[tuple[str, str]]]],
    pipeline_entries: list[tuple[str, str]],
    *,
    on_pick: Callable[[str], None],
    default_type: str,
) -> list[ft.Control]:
    """Expansion tiles per group; one row expanded by default (group that contains default_type)."""
    nonempty: list[tuple[str, list[tuple[str, str]]]] = [(k, v) for k, v in grouped_units if v]
    if pipeline_entries:
        nonempty.append((_GRP_PIPELINES, list(pipeline_entries)))
    if not nonempty:
        return [
            ft.Text(
                "No unit types available for this graph.",
                size=12,
                color=ft.Colors.GREY_400,
            )
        ]

    expand_idx = 0
    for j, (_, items) in enumerate(nonempty):
        if any(t == default_type for t, _ in items):
            expand_idx = j
            break

    tiles: list[ft.Control] = []
    for idx, (gkey, items) in enumerate(nonempty):
        title = _display_group_title(gkey)
        is_pipeline_group = gkey == _GRP_PIPELINES
        rows: list[ft.Control] = []
        for name, desc in items:
            sub = (desc or "").strip() or name
            if len(sub) > _DESC_MAX_LEN:
                sub = sub[: _DESC_MAX_LEN - 1] + "…"

            def make_handler(n: str) -> Callable[[ft.ControlEvent], None]:
                def _h(_e: ft.ControlEvent) -> None:
                    on_pick(n)

                return _h

            rows.append(
                ft.ListTile(
                    leading=_leading_icon_for_add_row(name, is_pipeline=is_pipeline_group),
                    title=ft.Text(name, size=14, weight=ft.FontWeight.W_500),
                    subtitle=ft.Text(
                        sub,
                        size=11,
                        color=ft.Colors.GREY_400,
                        max_lines=3,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    dense=True,
                    on_click=make_handler(name),
                )
            )
        tiles.append(
            ft.ExpansionTile(
                title=ft.Text(f"{title} ({len(items)})", size=14),
                subtitle=ft.Text("Tap a row to select this type", size=10, color=ft.Colors.GREY_500),
                expanded=(idx == expand_idx),
                controls=rows,
                tile_padding=ft.padding.symmetric(horizontal=4, vertical=2),
                controls_padding=ft.padding.only(left=8),
            )
        )
    return tiles

# Type names used only for extra-params UI (which form to show)
TYPE_RL_GYM = "RLGym"
TYPE_RL_ORACLE = "RLOracle"
TYPE_RL_SET = "RLSet"
TYPE_LLM_SET = "LLMSet"
TYPE_RL_AGENT = "RLAgent"
TYPE_LLM_AGENT = "LLMAgent"


def _runtime_from_summary(graph_summary: dict[str, Any]) -> str | None:
    """Return runtime key from graph summary. None if canonical, else e.g. node_red."""
    origin = graph_summary.get("origin") or {}
    if isinstance(origin, dict) and origin.get("node_red"):
        return "node_red"
    return None


def _unit_ids_from_summary(graph_summary: dict[str, Any], pipeline_type_names: set[str]) -> list[str]:
    """Return ordered list of unit ids for observation/action wiring (exclude pipelines and agents)."""
    units = graph_summary.get("units") or []
    exclude = set(pipeline_type_names) | {TYPE_RL_AGENT, TYPE_LLM_AGENT}
    return [u["id"] for u in units if isinstance(u, dict) and u.get("type") not in exclude]


def open_add_node_dialog(
    page: ft.Page,
    graph_summary: dict[str, Any],
    current_graph: Any,
    on_saved: Callable[[Any], None],
) -> None:
    """Open dialog to add a new unit (node). On Save calls on_saved(new_graph).

    Type list is resolved from the units_library workflow (no core dependency).
    graph_summary: LLM-style summary dict (units, connections, origin, environments, etc.).
    current_graph: graph dict or ProcessGraph for applying the edit; can be None for new graph.
    """
    from gui.components.workflow.edit_workflows.runner import apply_edit_via_workflow

    unit_entries, pipeline_entries = get_units_library_type_lists(graph_summary)
    if not unit_entries and not pipeline_entries:
        unit_entries = [
            ("Source", "Constant boundary / setpoint source for the process."),
            ("Valve", "Actuated valve; connects tanks and sources."),
            ("Tank", "Volume with temperature and flow state."),
            ("Sensor", "Measurement tap on the graph."),
        ]
    unit_names = {t for t, _ in unit_entries}
    pipeline_names = {t for t, _ in pipeline_entries}
    runtime = _runtime_from_summary(graph_summary)
    unit_ids = _unit_ids_from_summary(graph_summary, pipeline_names)

    default_type = (
        unit_entries[0][0]
        if unit_entries
        else (pipeline_entries[0][0] if pipeline_entries else "")
    )

    try:
        from units.registry import ensure_full_unit_registry, get_unit_spec as _get_unit_spec

        ensure_full_unit_registry()
    except Exception:

        def _get_unit_spec(_n: str) -> Any:  # type: ignore[misc]
            return None

    grouped_units = _group_units_for_add_dialog(unit_entries, graph_summary, _get_unit_spec)
    selected_type_ref: list[str] = [default_type]

    # Refs for extra params (must exist before _sync_extra_for_type references them)
    extra_refs: dict[str, ft.Ref[ft.TextField]] = {}
    extra_column_ref = ft.Ref[ft.Column]()

    id_field = ft.TextField(label="Id", hint_text="e.g. my_valve", autofocus=True)
    selected_type_display = ft.Text(
        f"Selected type: {default_type}",
        size=13,
        weight=ft.FontWeight.W_600,
    )
    controllable_check = ft.Checkbox(label="Controllable", value=False)
    controllable_row = ft.Row([controllable_check], wrap=False)

    # Extra params column (visibility and content updated on type change)
    extra_column = ft.Column(ref=extra_column_ref, controls=[], tight=True, visible=False)

    def _sync_extra_for_type(utype: str | None) -> None:
        content = _build_extra_content(utype, runtime, unit_ids, extra_refs)
        if content is None:
            if extra_column_ref.current:
                extra_column_ref.current.controls = []
                extra_column_ref.current.visible = False
            controllable_check.visible = True
        else:
            if extra_column_ref.current:
                extra_column_ref.current.controls = content.controls
                extra_column_ref.current.visible = True
            controllable_check.visible = utype in unit_names

    def _select_type(name: str) -> None:
        selected_type_ref[0] = name
        selected_type_display.value = f"Selected type: {name}"
        selected_type_display.update()
        _sync_extra_for_type(name)
        page.update()

    type_picker_body = ft.Column(
        controls=_build_expansion_type_pickers(
            grouped_units,
            pipeline_entries,
            on_pick=_select_type,
            default_type=default_type,
        ),
        spacing=4,
        tight=True,
        scroll=ft.ScrollMode.AUTO,
        height=340,
        width=440,
    )

    def save(_e: ft.ControlEvent) -> None:
        uid = (id_field.value or "").strip()
        if not uid:
            id_field.error_text = "Required"
            id_field.update()
            return
        utype = selected_type_ref[0] or (unit_entries[0][0] if unit_entries else "Valve")
        params: dict = {}
        if utype in unit_names:
            params = {}
        elif utype == TYPE_RL_GYM:
            params = _params_rlgym(extra_refs)
        elif utype == TYPE_RL_ORACLE:
            params = _params_rloracle(extra_refs)
        elif utype in (TYPE_RL_SET, TYPE_RL_AGENT):
            params = _params_rlagent(extra_refs)
        elif utype in (TYPE_LLM_SET, TYPE_LLM_AGENT):
            params = _params_llmagent(extra_refs)

        if utype in pipeline_names:
            edit = {"action": "add_pipeline", "pipeline": {"id": uid, "type": utype, "params": params}}
        else:
            edit = {
                "action": "add_unit",
                "unit": {
                    "id": uid,
                    "type": utype,
                    "controllable": controllable_check.value if utype in unit_names else False,
                    "params": params,
                },
            }
        graph_input: Any = (
            {"environment_type": "thermodynamic", "units": [], "connections": []}
            if current_graph is None
            else current_graph
        )
        try:
            new_graph = apply_edit_via_workflow(graph_input, edit)
        except ValueError as err:
            id_field.error_text = str(err)
            id_field.update()
            return
        _close_dlg()
        on_saved(new_graph)

    def _close_dlg() -> None:
        dlg.open = False
        page.update()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Add node"),
        content=ft.Container(
            content=ft.Column(
                [
                    id_field,
                    ft.Text("Type", size=12, color=ft.Colors.GREY_400),
                    selected_type_display,
                    type_picker_body,
                    controllable_row,
                    extra_column,
                ],
                tight=True,
                width=460,
            ),
        ),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: _close_dlg()),
            ft.TextButton("Save", on_click=save),
        ],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
    _sync_extra_for_type(default_type)
    page.update()


def _build_extra_content(
    utype: str | None,
    runtime: str | None,
    unit_ids: list[str],
    refs: dict[str, ft.Ref[ft.TextField]],
) -> ft.Column | None:
    """Build optional params UI for RLGym / RLOracle / RLSet / LLMSet / RLAgent / LLMAgent. Returns None for process types."""
    if utype not in (TYPE_RL_GYM, TYPE_RL_ORACLE, TYPE_RL_SET, TYPE_LLM_SET, TYPE_RL_AGENT, TYPE_LLM_AGENT):
        return None
    refs.clear()
    hint = "e.g. " + ", ".join(unit_ids[:3]) if unit_ids else "unit_id1, unit_id2"
    controls: list[ft.Control] = []
    for key, label, hint_text, value in [
        ("obs_ids", "Observation source ids", hint, ""),
        ("act_ids", "Action target ids", hint, ""),
    ]:
        refs[key] = ft.Ref[ft.TextField]()
        controls.append(ft.TextField(ref=refs[key], label=label, hint_text=hint_text, value=value))
    if utype in (TYPE_RL_GYM, TYPE_RL_ORACLE):
        refs["max_steps"] = ft.Ref[ft.TextField]()
        controls.append(ft.TextField(ref=refs["max_steps"], label="Max steps", value="600", keyboard_type=ft.KeyboardType.NUMBER))
    if utype == TYPE_RL_GYM:
        pass  # obs/act/max_steps only
    elif utype == TYPE_RL_ORACLE:
        pass  # no extra fields beyond obs/act/max_steps
    elif utype in (TYPE_RL_SET, TYPE_RL_AGENT):
        refs["inference_url"] = ft.Ref[ft.TextField]()
        refs["model_path"] = ft.Ref[ft.TextField]()
        controls.append(ft.TextField(ref=refs["inference_url"], label="Inference URL", value="http://127.0.0.1:8000/predict"))
        controls.append(ft.TextField(ref=refs["model_path"], label="Model path (optional)", value=""))
    elif utype in (TYPE_LLM_SET, TYPE_LLM_AGENT):
        refs["model_name"] = ft.Ref[ft.TextField]()
        refs["provider"] = ft.Ref[ft.TextField]()
        refs["system_prompt"] = ft.Ref[ft.TextField]()
        refs["inference_url_llm"] = ft.Ref[ft.TextField]()
        controls.append(ft.TextField(ref=refs["model_name"], label="Model name", value="llama3.2"))
        controls.append(ft.TextField(ref=refs["provider"], label="Provider", value="ollama"))
        controls.append(ft.TextField(
            ref=refs["system_prompt"],
            label="System prompt",
            value="You are a control agent. Output JSON with key 'action' and a list of numbers.",
            multiline=True,
            min_lines=2,
        ))
        controls.append(ft.TextField(ref=refs["inference_url_llm"], label="Inference URL (optional)", value="http://127.0.0.1:8001/predict"))
    return ft.Column(controls, tight=True)


def _get_extra_value(refs: dict[str, ft.Ref[ft.TextField]], key: str) -> str:
    """Read value from the TextField ref for key."""
    r = refs.get(key)
    if r is None or r.current is None:
        return ""
    return (r.current.value or "").strip()


def _parse_comma_ids(s: str) -> list[str]:
    """Parse comma-separated ids into a list (order preserved)."""
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _params_rlgym(refs: dict[str, ft.Ref[ft.TextField]]) -> dict:
    """Params for RLGym: observation_source_ids, action_target_ids, max_steps."""
    obs_s = _get_extra_value(refs, "obs_ids")
    act_s = _get_extra_value(refs, "act_ids")
    max_steps_s = _get_extra_value(refs, "max_steps")
    obs_ids = _parse_comma_ids(obs_s)
    act_ids = _parse_comma_ids(act_s)
    max_steps = 600
    try:
        max_steps = int(max_steps_s) if max_steps_s else 600
    except ValueError:
        pass
    return {
        "observation_source_ids": obs_ids,
        "action_target_ids": act_ids,
        "max_steps": max_steps,
    }


def _params_rloracle(refs: dict[str, ft.Ref[ft.TextField]]) -> dict:
    obs_s = _get_extra_value(refs, "obs_ids")
    act_s = _get_extra_value(refs, "act_ids")
    max_steps_s = _get_extra_value(refs, "max_steps")
    obs_ids = _parse_comma_ids(obs_s)
    act_ids = _parse_comma_ids(act_s)
    max_steps = 600
    try:
        max_steps = int(max_steps_s) if max_steps_s else 600
    except ValueError:
        pass
    observation_spec = [{"name": n} for n in obs_ids]
    action_spec = [{"name": n} for n in act_ids]
    adapter_config = {
        "observation_spec": observation_spec,
        "action_spec": action_spec,
        "max_steps": max_steps,
    }
    return {
        "observation_source_ids": obs_ids,
        "action_target_ids": act_ids,
        "adapter_config": adapter_config,
    }


def _params_rlagent(refs: dict[str, ft.Ref[ft.TextField]]) -> dict:
    obs_s = _get_extra_value(refs, "obs_ids")
    act_s = _get_extra_value(refs, "act_ids")
    inference_url = _get_extra_value(refs, "inference_url") or "http://127.0.0.1:8000/predict"
    model_path = _get_extra_value(refs, "model_path")
    obs_ids = _parse_comma_ids(obs_s)
    act_ids = _parse_comma_ids(act_s)
    params: dict = {
        "observation_source_ids": obs_ids,
        "action_target_ids": act_ids,
        "inference_url": inference_url,
    }
    if model_path:
        params["model_path"] = model_path
    return params


def _params_llmagent(refs: dict[str, ft.Ref[ft.TextField]]) -> dict:
    obs_s = _get_extra_value(refs, "obs_ids")
    act_s = _get_extra_value(refs, "act_ids")
    model_name = _get_extra_value(refs, "model_name") or "llama3.2"
    provider = _get_extra_value(refs, "provider") or "ollama"
    system_prompt = _get_extra_value(refs, "system_prompt") or "You are a control agent. Output JSON with key 'action' and a list of numbers."
    inference_url = _get_extra_value(refs, "inference_url_llm")
    obs_ids = _parse_comma_ids(obs_s)
    act_ids = _parse_comma_ids(act_s)
    params: dict = {
        "observation_source_ids": obs_ids,
        "action_target_ids": act_ids,
        "model_name": model_name,
        "provider": provider,
        "system_prompt": system_prompt,
    }
    if inference_url:
        params["inference_url"] = inference_url
    return params
