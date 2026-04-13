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


def _unit_ids_from_summary(graph_summary: dict[str, Any], pipeline_types: list[str]) -> list[str]:
    """Return ordered list of unit ids for observation/action wiring (exclude pipelines and agents)."""
    units = graph_summary.get("units") or []
    exclude = set(pipeline_types) | {TYPE_RL_AGENT, TYPE_LLM_AGENT}
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

    unit_types, pipeline_types = get_units_library_type_lists(graph_summary)
    if not unit_types and not pipeline_types:
        unit_types = ["Source", "Valve", "Tank", "Sensor"]
    runtime = _runtime_from_summary(graph_summary)
    unit_ids = _unit_ids_from_summary(graph_summary, pipeline_types)

    # Library already filtered by graph; show as-is (no extra filtering or labels)
    type_options = [ft.dropdown.Option(key=t, text=t) for t in unit_types]
    type_options.extend(ft.dropdown.Option(key=t, text=t) for t in pipeline_types)

    default_type = unit_types[0] if unit_types else (pipeline_types[0] if pipeline_types else "")

    # Refs for extra params (must exist before type_dropdown on_change references them)
    extra_refs: dict[str, ft.Ref[ft.TextField]] = {}
    extra_column_ref = ft.Ref[ft.Column]()

    id_field = ft.TextField(label="Id", hint_text="e.g. my_valve", autofocus=True)
    type_dropdown = ft.Dropdown(
        label="Type",
        options=type_options,
        value=default_type,
        width=280,
    )
    controllable_check = ft.Checkbox(label="Controllable", value=False)
    controllable_row = ft.Row([controllable_check], wrap=False)

    # Extra params column (visibility and content updated on type change)
    extra_column = ft.Column(ref=extra_column_ref, controls=[], tight=True, visible=False)

    def _on_type_changed(e: ft.ControlEvent | None = None) -> None:
        utype = type_dropdown.value
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
            controllable_check.visible = utype in unit_types
        page.update()

    type_dropdown.on_change = _on_type_changed

    def save(_e: ft.ControlEvent) -> None:
        uid = (id_field.value or "").strip()
        if not uid:
            id_field.error_text = "Required"
            id_field.update()
            return
        utype = type_dropdown.value or (unit_types[0] if unit_types else "Valve")
        params: dict = {}
        if utype in unit_types:
            params = {}
        elif utype == TYPE_RL_GYM:
            params = _params_rlgym(extra_refs)
        elif utype == TYPE_RL_ORACLE:
            params = _params_rloracle(extra_refs)
        elif utype in (TYPE_RL_SET, TYPE_RL_AGENT):
            params = _params_rlagent(extra_refs)
        elif utype in (TYPE_LLM_SET, TYPE_LLM_AGENT):
            params = _params_llmagent(extra_refs)

        if utype in pipeline_types:
            edit = {"action": "add_pipeline", "pipeline": {"id": uid, "type": utype, "params": params}}
        else:
            edit = {
                "action": "add_unit",
                "unit": {"id": uid, "type": utype, "controllable": controllable_check.value if utype in unit_types else False, "params": params},
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
                    type_dropdown,
                    controllable_row,
                    extra_column,
                ],
                tight=True,
                width=280,
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
