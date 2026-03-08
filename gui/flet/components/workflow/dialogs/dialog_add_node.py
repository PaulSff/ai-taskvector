"""
Dialog to add a node (unit) to the process graph.

Supports process units (Source, Valve, Tank, Sensor) and, depending on runtime,
RLGym (our runtime training), RLOracle (external Node-RED/n8n), RLAgent, and LLMAgent.
"""
from __future__ import annotations

from typing import Callable

import flet as ft

from schemas.process_graph import ProcessGraph

from gui.flet.components.workflow.dialogs.dialog_common import dict_to_graph, graph_to_dict

# Process (simulator) unit types
UNIT_TYPES_PROCESS = ["Source", "Valve", "Tank", "Sensor"]

# Agent / Oracle / Gym types shown when graph has units to wire
TYPE_RL_GYM = "RLGym"
TYPE_RL_ORACLE = "RLOracle"
TYPE_RL_SET = "RLSet"
TYPE_LLM_SET = "LLMSet"
TYPE_RL_AGENT = "RLAgent"
TYPE_LLM_AGENT = "LLMAgent"


def _runtime_from_graph(graph: ProcessGraph | None) -> str | None:
    """Return runtime key from graph (centralized). None if canonical, else type from graph (e.g. node_red, n8n)."""
    if graph is None:
        return None
    from normalizer.runtime_detector import is_external_runtime, runtime_label

    if not is_external_runtime(graph):
        return None
    return runtime_label(graph)


def _unit_ids_from_graph(graph: ProcessGraph | None) -> list[str]:
    """Return ordered list of unit ids for observation/action wiring (exclude agent/oracle)."""
    if graph is None:
        return []
    exclude_types = (TYPE_RL_GYM, TYPE_RL_ORACLE, TYPE_RL_AGENT, TYPE_LLM_AGENT)
    return [u.id for u in graph.units if u.type not in exclude_types]


def open_add_node_dialog(
    page: ft.Page,
    current_graph: ProcessGraph | None,
    on_saved: Callable[[ProcessGraph], None],
) -> None:
    """Open dialog to add a new unit (node). On Save calls on_saved(new_graph)."""
    from assistants.graph_edits import PIPELINE_TYPES, apply_graph_edit

    runtime = _runtime_from_graph(current_graph)
    unit_ids = _unit_ids_from_graph(current_graph)

    # Build type options: process units; pipelines (RLGym, RLOracle, RLSet, LLMSet); units (RLAgent, LLMAgent)
    type_options = [ft.dropdown.Option(key=t, text=t) for t in UNIT_TYPES_PROCESS]
    if unit_ids:
        type_options.append(ft.dropdown.Option(key=TYPE_RL_GYM, text=TYPE_RL_GYM + " (training)"))
    if runtime in ("node_red", "n8n"):
        type_options.append(ft.dropdown.Option(key=TYPE_RL_ORACLE, text=TYPE_RL_ORACLE + " (external)"))
    if runtime or unit_ids:
        type_options.append(ft.dropdown.Option(key=TYPE_RL_SET, text=TYPE_RL_SET + " (pipeline)"))
        type_options.append(ft.dropdown.Option(key=TYPE_LLM_SET, text=TYPE_LLM_SET + " (pipeline)"))
        type_options.append(ft.dropdown.Option(key=TYPE_RL_AGENT, text=TYPE_RL_AGENT))
        type_options.append(ft.dropdown.Option(key=TYPE_LLM_AGENT, text=TYPE_LLM_AGENT))

    # Refs for extra params (must exist before type_dropdown on_change references them)
    extra_refs: dict[str, ft.Ref[ft.TextField]] = {}
    extra_column_ref = ft.Ref[ft.Column]()

    id_field = ft.TextField(label="Id", hint_text="e.g. my_valve", autofocus=True)
    type_dropdown = ft.Dropdown(
        label="Type",
        options=type_options,
        value=UNIT_TYPES_PROCESS[1],
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
            controllable_check.visible = utype in UNIT_TYPES_PROCESS
        page.update()

    type_dropdown.on_change = _on_type_changed

    def save(_e: ft.ControlEvent) -> None:
        uid = (id_field.value or "").strip()
        if not uid:
            id_field.error_text = "Required"
            id_field.update()
            return
        utype = type_dropdown.value or "Valve"
        params: dict = {}
        if utype in UNIT_TYPES_PROCESS:
            params = {}
        elif utype == TYPE_RL_GYM:
            params = _params_rlgym(extra_refs)
        elif utype == TYPE_RL_ORACLE:
            params = _params_rloracle(extra_refs)
        elif utype in (TYPE_RL_SET, TYPE_RL_AGENT):
            params = _params_rlagent(extra_refs)
        elif utype in (TYPE_LLM_SET, TYPE_LLM_AGENT):
            params = _params_llmagent(extra_refs)

        if utype in PIPELINE_TYPES:
            edit = {"action": "add_pipeline", "pipeline": {"id": uid, "type": utype, "params": params}}
        else:
            edit = {
                "action": "add_unit",
                "unit": {"id": uid, "type": utype, "controllable": controllable_check.value if utype in UNIT_TYPES_PROCESS else False, "params": params},
            }
        if current_graph is None:
            base = {"environment_type": "thermodynamic", "units": [], "connections": []}
            updated = apply_graph_edit(base, edit)
            new_graph = dict_to_graph(updated)
        else:
            graph_dict = graph_to_dict(current_graph)
            try:
                updated = apply_graph_edit(graph_dict, edit)
                new_graph = dict_to_graph(updated)
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
