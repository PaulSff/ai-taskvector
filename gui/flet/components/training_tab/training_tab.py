"""
Training tab: AI Student (from graph), Goals, Rewards (DSL from training config), Training progress.

Observations and action targets are derived from the graph automatically:
- When the graph has an RLAgent or LLMAgent, they come from connections (who connects to/from the agent).
- When the graph has an RLGym unit only, they come from params (observation_source_ids, action_target_ids).
See core.schemas.agent_node: get_agent_observation_input_ids, get_agent_action_output_ids.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import flet as ft

from gui.flet.tools.code_editor import build_code_editor

from core.schemas.agent_node import (
    get_agent_action_output_ids,
    get_agent_observation_input_ids,
    get_policy_node,
)
from core.schemas.process_graph import ProcessGraph
from core.schemas.training_config import GoalConfig, RewardsConfig, TrainingConfig
from gui.flet.components.settings import get_best_model_path, get_training_config_path, save_settings
from gui.flet.components.workflow.core_workflows import run_runtime_label

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_DEFAULT_TRAINING_CONFIG_PATH = "config/examples/training_config.yaml"
_RUN_RL_TRAINING_WORKFLOW_PATH = _REPO_ROOT / "gui" / "flet" / "components" / "workflow" / "tools" / "run_rl_training.json"


def _resolve_config_path(path_str: str) -> Path:
    """Resolve path to absolute; if relative, interpret relative to repo root."""
    path_str = (path_str or "").strip()
    if not path_str:
        return _REPO_ROOT / _DEFAULT_TRAINING_CONFIG_PATH
    p = Path(path_str)
    if p.is_absolute():
        return p
    return (_REPO_ROOT / path_str).resolve()


def _load_training_config(path: Path | str) -> TrainingConfig | None:
    if not path:
        return None
    path = Path(path)
    if not path.is_file():
        return None
    try:
        from core.normalizer import load_training_config_from_file
        return load_training_config_from_file(path)
    except Exception:
        return None


def _build_ai_student_section(
    page: ft.Page,
    graph_ref: list[ProcessGraph | None],
) -> tuple[ft.Control, Any]:
    """AI Student: unit type/name, observations, action targets, runtime, inference, conceptual scheme."""
    title = ft.Text("1. AI Student", size=16, weight=ft.FontWeight.BOLD)
    unit_type_txt = ft.Text("—", size=12)
    unit_name_txt = ft.Text("—", size=12)
    obs_txt = ft.Text("—", size=12)
    actions_txt = ft.Text("—", size=12)
    runtime_txt = ft.Text("—", size=12)
    inference_txt = ft.Text("—", size=12)
    scheme_txt = ft.Text("Observations → [Agent] → Action targets", size=11, color=ft.Colors.GREY_600)

    def refresh() -> None:
        graph = graph_ref[0] if graph_ref else None
        if graph is None:
            unit_type_txt.value = "No graph loaded"
            unit_name_txt.value = ""
            obs_txt.value = "—"
            actions_txt.value = "—"
            runtime_txt.value = "—"
            inference_txt.value = "—"
            scheme_txt.value = "Load a workflow with RLAgent/LLMAgent to see wiring."
        else:
            policy = get_policy_node(graph)
            if policy is None:
                unit_type_txt.value = "No RLAgent/LLMAgent in graph"
                unit_name_txt.value = ""
                obs_txt.value = "—"
                actions_txt.value = "—"
            else:
                unit_type_txt.value = policy.type
                unit_name_txt.value = policy.name or policy.id or "—"
                obs_ids = get_agent_observation_input_ids(graph)
                act_ids = get_agent_action_output_ids(graph)
                obs_txt.value = ", ".join(obs_ids) if obs_ids else "—"
                actions_txt.value = ", ".join(act_ids) if act_ids else "—"
            label, is_native = run_runtime_label(graph)
            runtime_txt.value = "Native" if is_native else f"External ({label})"
            if policy and policy.params:
                inf_url = policy.params.get("inference_url")
                model_path = policy.params.get("model_path")
                provider = policy.params.get("provider")
                model_name = policy.params.get("model_name")
                if inf_url or model_path:
                    inference_txt.value = f"Server: {inf_url or 'N/A'}  Model: {model_path or 'N/A'}"
                elif provider or model_name:
                    inference_txt.value = f"Inline ({provider or 'ollama'} / {model_name or 'N/A'})"
                else:
                    inference_txt.value = "Inline (default)"
            else:
                inference_txt.value = "—"
            scheme_txt.value = f"Observations ({'native' if run_runtime_label(graph)[1] else 'external'}) → {policy.type if policy else '?'} → Action targets ({'native' if run_runtime_label(graph)[1] else 'external'})"
        try:
            unit_type_txt.update()
            unit_name_txt.update()
            obs_txt.update()
            actions_txt.update()
            runtime_txt.update()
            inference_txt.update()
            scheme_txt.update()
        except Exception:
            pass

    refresh_btn = ft.ElevatedButton("Refresh from graph", on_click=lambda _: refresh())

    return ft.Container(
        content=ft.Column(
            [
                title,
                ft.Row([ft.Text("Unit type: ", size=12), unit_type_txt], wrap=True),
                ft.Row([ft.Text("Name: ", size=12), unit_name_txt], wrap=True),
                ft.Row([ft.Text("Observations: ", size=12), obs_txt], wrap=True),
                ft.Row([ft.Text("Action targets: ", size=12), actions_txt], wrap=True),
                ft.Row([ft.Text("Runtime: ", size=12), runtime_txt], wrap=True),
                ft.Row([ft.Text("Inference: ", size=12), inference_txt], wrap=True),
                scheme_txt,
                refresh_btn,
            ],
            spacing=6,
            alignment=ft.MainAxisAlignment.START,
        ),
        padding=12,
    ), refresh


def _build_goals_section(goal: GoalConfig | None) -> ft.Control:
    """Goals from training config."""
    title = ft.Text("2. Goals", size=16, weight=ft.FontWeight.BOLD)
    if goal is None:
        content = ft.Text("Load a training config to see goals.", size=12, color=ft.Colors.GREY_600)
    else:
        lines = []
        if goal.target_temp is not None:
            lines.append(f"Target temp: {goal.target_temp} °C")
        if goal.target_volume_ratio:
            lines.append(f"Volume ratio: {goal.target_volume_ratio[0]}–{goal.target_volume_ratio[1]}")
        if goal.target_pressure_range:
            lines.append(f"Pressure range: {goal.target_pressure_range}")
        if goal.target_metric:
            lines.append(f"Target metric: {goal.target_metric}")
        content = ft.Text("\n".join(lines) if lines else "Default (setpoint)", size=12)
    return ft.Container(
        content=ft.Column([title, content], spacing=6, alignment=ft.MainAxisAlignment.START),
        padding=12,
    )


def _build_rewards_section(rewards: RewardsConfig | None) -> ft.Control:
    """Rewards (DSL): preset, formula, rules from training config."""
    title = ft.Text("3. Rewards (DSL)", size=16, weight=ft.FontWeight.BOLD)
    if rewards is None:
        content = ft.Text("Load a training config to see rewards.", size=12, color=ft.Colors.GREY_600)
    else:
        parts = [ft.Text(f"Preset: {rewards.preset}", size=12)]
        if rewards.formula:
            for c in rewards.formula:
                parts.append(ft.Text(f"  • {c.expr}  (weight={c.weight}, reward={c.reward})", size=11))
        if rewards.rules:
            for r in rewards.rules:
                parts.append(ft.Text(f"  Rule: {r.condition} → {r.reward_delta}", size=11))
        content = ft.Column(parts, spacing=4)
    return ft.Container(
        content=ft.Column([title, content], spacing=6, alignment=ft.MainAxisAlignment.START),
        padding=12,
    )


def _build_training_progress_section(
    page: ft.Page,
    config_path_ref: list[str],
    config_ref: list[TrainingConfig | None],
) -> ft.Control:
    """Run episodes button, progress bar, stats placeholder, best model path."""
    title = ft.Text("4. Training progress", size=16, weight=ft.FontWeight.BOLD)
    progress_bar = ft.ProgressBar(visible=False, width=400)
    status_txt = ft.Text("", size=12)
    best_model_txt = ft.Text(get_best_model_path() or "—", size=12)
    stats_txt = ft.Text("Stats from last run (placeholder).", size=11, color=ft.Colors.GREY_600)

    def on_run(_e: ft.ControlEvent) -> None:
        path = config_path_ref[0] if config_path_ref else _DEFAULT_TRAINING_CONFIG_PATH
        resolved = _resolve_config_path(path)
        if not resolved.is_file():
            page.snack_bar = ft.SnackBar(content=ft.Text("Set and load a valid training config path first."), open=True)
            page.update()
            return
        progress_bar.visible = True
        status_txt.value = "Training…"
        progress_bar.update()
        status_txt.update()
        page.update()

        config_path_str = str(resolved)

        async def run_async() -> None:
            try:
                try:
                    from units.data_bi import register_data_bi_units
                    register_data_bi_units()
                except Exception:
                    pass
                from runtime.run import run_workflow

                def do_run() -> dict[str, Any]:
                    return run_workflow(
                        _RUN_RL_TRAINING_WORKFLOW_PATH,
                        initial_inputs={
                            "inject_action": {
                                "data": {
                                    "action": "run_rl_training",
                                    "config_path": config_path_str,
                                }
                            }
                        },
                        format="dict",
                    )

                loop = asyncio.get_event_loop()
                outputs = await loop.run_in_executor(None, do_run)
                out = (outputs or {}).get("run_rl_training") or {}
                result = out.get("result") or {}
                err = out.get("error")
                if err:
                    status_txt.value = f"Error: {err[:120]}"
                    best_model_txt.value = "—"
                else:
                    status_txt.value = result.get("message") or "Training complete."
                    path_val = result.get("best_model_save_path") or ""
                    best_model_txt.value = path_val or "—"
                    if path_val:
                        try:
                            save_settings(best_model_path=path_val)
                        except Exception:
                            pass
            except Exception as ex:
                status_txt.value = f"Error: {ex}"
                best_model_txt.value = "—"
            progress_bar.visible = False
            progress_bar.update()
            status_txt.update()
            best_model_txt.update()
            page.update()
            page.snack_bar = ft.SnackBar(content=ft.Text(status_txt.value[:80]), open=True)
            page.update()

        page.run_task(run_async)

    run_btn = ft.ElevatedButton("Run episodes", on_click=on_run)
    return ft.Container(
        content=ft.Column(
            [
                title,
                run_btn,
                progress_bar,
                status_txt,
                ft.Row([ft.Text("Best model path: ", size=12), best_model_txt], wrap=True),
                stats_txt,
                ft.Text("Comparison to previous (placeholder).", size=11, color=ft.Colors.GREY_600),
            ],
            spacing=8,
            alignment=ft.MainAxisAlignment.START,
        ),
        padding=12,
    )


def build_training_tab(
    page: ft.Page,
    graph_ref: list[ProcessGraph | None] | None = None,
) -> ft.Control:
    """
    Build the Training tab: AI Student, Goals, Rewards (DSL), Training progress.
    graph_ref: optional list of one element holding the current process graph (so AI Student can show unit, obs, actions, runtime).
    """
    graph_ref = graph_ref or [None]
    config_path_ref: list[str] = [get_training_config_path() or _DEFAULT_TRAINING_CONFIG_PATH]
    config_ref: list[TrainingConfig | None] = [None]

    config_path_tf = ft.TextField(
        label="Training config path",
        value=config_path_ref[0],
        width=500,
        text_style=ft.TextStyle(font_family="monospace", size=11),
    )

    goals_section = _build_goals_section(None)
    rewards_section = _build_rewards_section(None)

    def on_load_config(_e: ft.ControlEvent) -> None:
        path = (config_path_tf.value or "").strip()
        if not path:
            return
        config_path_ref[0] = path
        cfg = _load_training_config(_resolve_config_path(path))
        config_ref[0] = cfg
        if cfg is None:
            page.snack_bar = ft.SnackBar(content=ft.Text("Failed to load config or file not found."), open=True)
        else:
            # Rebuild goals and rewards body from new config
            goals_section.content.controls[1] = _build_goals_section(cfg.goal).content.controls[1]
            rewards_section.content.controls[1] = _build_rewards_section(cfg.rewards).content.controls[1]
            goals_section.content.update()
            rewards_section.content.update()
            page.snack_bar = ft.SnackBar(content=ft.Text("Config loaded."), open=True)
            try:
                save_settings(training_config_path=path)
            except Exception:
                pass
        page.update()

    load_btn = ft.ElevatedButton("Load config", on_click=on_load_config)

    ai_student_container, refresh_ai_student = _build_ai_student_section(page, graph_ref)
    refresh_ai_student()

    progress_section = _build_training_progress_section(page, config_path_ref, config_ref)

    # Dashboard view: config path, AI Student, Goals, Rewards, Progress
    dashboard_column = ft.Column(
        [
            ft.Row([config_path_tf, load_btn], wrap=True),
            ai_student_container,
            goals_section,
            rewards_section,
            progress_section,
        ],
        spacing=16,
        alignment=ft.MainAxisAlignment.START,
        scroll=ft.ScrollMode.AUTO,
    )
    dashboard_content = ft.Container(content=dashboard_column, padding=24, expand=True)

    view_mode: list[str] = ["dashboard"]
    code_view_container = ft.Container(expand=True, content=ft.Text("Code", color=ft.Colors.GREY_500))

    def build_code_view_content() -> ft.Control:
        """Build code view: editable training_config YAML + Back to Dashboard + Apply."""
        path = config_path_ref[0] if config_path_ref else ""
        resolved = _resolve_config_path(path)
        if resolved.is_file():
            try:
                raw = resolved.read_text(encoding="utf-8")
            except Exception:
                raw = "# Failed to read file."
        else:
            raw = "# No file loaded.\n# Set the training config path above (Dashboard) and click Load config, or open a YAML file."

        code_editor_control, get_value, _show_find, _hide_find = build_code_editor(
            raw,
            expand=True,
            page=page,
            language="yaml",
        )

        def back_to_dashboard(_e: ft.ControlEvent) -> None:
            show_dashboard_view(None)

        def apply_code(_e: ft.ControlEvent) -> None:
            try:
                page.update()
            except Exception:
                pass
            text = (get_value() or "").strip()
            if not text or text.startswith("# No file loaded"):
                page.snack_bar = ft.SnackBar(content=ft.Text("Nothing to apply or no file path set."), open=True)
                page.update()
                return
            resolved = _resolve_config_path(path)
            if not path or not resolved.is_file():
                page.snack_bar = ft.SnackBar(content=ft.Text("Set a valid config path in Dashboard first."), open=True)
                page.update()
                return
            try:
                from core.normalizer import to_training_config
                to_training_config(text, format="yaml")
            except Exception as ex:
                page.snack_bar = ft.SnackBar(content=ft.Text(f"Invalid YAML or config: {ex}"), open=True)
                page.update()
                return
            try:
                resolved.write_text(text, encoding="utf-8")
            except Exception as ex:
                page.snack_bar = ft.SnackBar(content=ft.Text(f"Save failed: {ex}"), open=True)
                page.update()
                return
            cfg = _load_training_config(resolved)
            config_ref[0] = cfg
            if cfg is not None:
                goals_section.content.controls[1] = _build_goals_section(cfg.goal).content.controls[1]
                rewards_section.content.controls[1] = _build_rewards_section(cfg.rewards).content.controls[1]
                goals_section.content.update()
                rewards_section.content.update()
            try:
                save_settings(training_config_path=path)
            except Exception:
                pass
            page.snack_bar = ft.SnackBar(content=ft.Text("Config saved."), open=True)
            page.update()

        return ft.Column(
            [
                ft.Container(
                    content=ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.ARROW_BACK,
                                tooltip="Back to Dashboard",
                                on_click=back_to_dashboard,
                                icon_color=ft.Colors.PRIMARY,
                            ),
                            ft.TextButton(content="Apply", on_click=apply_code),
                            ft.Container(expand=True),
                        ],
                        spacing=8,
                    ),
                    bgcolor=ft.Colors.TRANSPARENT,
                    padding=8,
                ),
                ft.Container(
                    content=code_editor_control,
                    expand=True,
                    bgcolor=ft.Colors.TRANSPARENT,
                ),
            ],
            expand=True,
            spacing=0,
        )

    main_view = ft.Container(expand=True, content=dashboard_content)
    ACTIVE_ICON_COLOR = ft.Colors.GREY_200
    INACTIVE_ICON_COLOR = ft.Colors.GREY_500

    def update_view_tab_icons(active: str) -> None:
        dashboard_btn.icon_color = ACTIVE_ICON_COLOR if active == "dashboard" else INACTIVE_ICON_COLOR
        code_btn.icon_color = ACTIVE_ICON_COLOR if active == "code" else INACTIVE_ICON_COLOR
        dashboard_btn.update()
        code_btn.update()

    def show_dashboard_view(_e: ft.ControlEvent | None = None) -> None:
        view_mode[0] = "dashboard"
        main_view.content = dashboard_content
        update_view_tab_icons("dashboard")
        main_view.update()
        page.update()

    def show_code_view(_e: ft.ControlEvent) -> None:
        view_mode[0] = "code"
        code_view_container.content = build_code_view_content()
        main_view.content = code_view_container
        update_view_tab_icons("code")
        main_view.update()
        page.update()

    dashboard_btn = ft.IconButton(
        icon=ft.Icons.DASHBOARD_ROUNDED,
        tooltip="Dashboard",
        on_click=show_dashboard_view,
        icon_color=ACTIVE_ICON_COLOR,
    )
    code_btn = ft.IconButton(
        icon=ft.Icons.CODE,
        tooltip="Code",
        on_click=show_code_view,
        icon_color=INACTIVE_ICON_COLOR,
    )

    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Training", size=20, weight=ft.FontWeight.BOLD),
                        ft.Container(expand=True),
                        dashboard_btn,
                        code_btn,
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    spacing=8,
                ),
                main_view,
            ],
            spacing=12,
            expand=True,
        ),
        padding=24,
        expand=True,
    )
