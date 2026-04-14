"""
Workflow tab bottom console: JSON output display, Run button (run_workflow + optional log grep),
and ``show_console_with_run_output`` for chat-driven runs.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable

import flet as ft

from assistants.tools.workflow_path import get_tool_workflow_path
from core.schemas.process_graph import ProcessGraph

from gui.components.settings import get_debug_log_path
from .run_console import (
    debug_log_param_overrides_for_graph_dict,
    format_run_outputs,
)
from gui.utils.code_editor import CODE_EDITOR_BG, build_code_display


@dataclass(frozen=True)
class WorkflowRunConsoleControls:
    """Console panel, toolbar Run control, and chat hook to mirror run output in the console."""

    console_container: ft.Container
    run_button: ft.IconButton
    show_console_with_run_output: Callable[..., None]


def build_workflow_run_console(
    page: ft.Page,
    graph_ref: list[ProcessGraph | None],
    show_toast: Callable[[ft.Page, str], None] | None,
) -> WorkflowRunConsoleControls:
    """Build the collapsible console, wire Run, and return ``show_console_with_run_output`` for main/chat."""

    CONSOLE_HEIGHT_FRACTION = 0.36
    CONSOLE_HEIGHT_FALLBACK = 200
    console_visible: list[bool] = [False]
    terminal_lines: list[str] = []
    _console_initial = "— Click Run to execute the workflow and see output. —"
    console_display_control, set_console_value, _ = build_code_display(
        _console_initial,
        language="json",
        expand=True,
        page=page,
    )

    def _append_console(text: str) -> None:
        terminal_lines.append(text)
        set_console_value("\n".join(terminal_lines) if terminal_lines else _console_initial)

    def _show_console() -> None:
        if not console_visible[0]:
            console_visible[0] = True
            try:
                h = getattr(page, "window_height", None) or getattr(
                    getattr(page, "window", None), "height", None
                )
                console_container.height = int((h or 0) * CONSOLE_HEIGHT_FRACTION) or CONSOLE_HEIGHT_FALLBACK
            except Exception:
                console_container.height = CONSOLE_HEIGHT_FALLBACK
            try:
                console_container.update()
            except Exception:
                pass

    def _close_console(_e: ft.ControlEvent) -> None:
        console_visible[0] = False
        console_container.height = 0
        try:
            console_container.update()
            page.update()
        except Exception:
            pass

    console_close_btn = ft.IconButton(
        icon=ft.Icons.CLOSE,
        icon_size=18,
        tooltip="Close console",
        on_click=_close_console,
        style=ft.ButtonStyle(padding=2),
    )
    console_data_container = ft.Container(
        content=console_display_control,
        expand=True,
        border=ft.border.all(1, ft.Colors.GREY_700),
        border_radius=4,
        padding=6,
        bgcolor=CODE_EDITOR_BG,
    )
    console_container = ft.Container(
        content=ft.Row(
            [
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text("Console", size=12, weight=ft.FontWeight.W_500, color=ft.Colors.GREY_400),
                                ft.Container(expand=True),
                                console_close_btn,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row(
                            [console_data_container],
                            expand=True,
                        ),
                    ],
                    expand=True,
                    spacing=4,
                ),
            ],
            expand=True,
        ),
        height=0,
        animate=ft.Animation(duration=200, curve=ft.AnimationCurve.EASE_OUT),
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )

    run_workflow_graph_json = get_tool_workflow_path("run_workflow")
    grep_workflow_json = get_tool_workflow_path("grep")

    def _on_run_click(_e: ft.ControlEvent) -> None:
        graph = graph_ref[0]
        if graph is None:
            if show_toast:

                async def _no_graph() -> None:
                    await show_toast(page, "No workflow loaded. Open or create a workflow first.")

                page.run_task(_no_graph)
            return
        _show_console()
        terminal_lines.clear()
        _append_console("Running workflow (via RunWorkflow unit)...")
        graph_dict = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else graph
        log_path_str = str(get_debug_log_path())
        deb_over = debug_log_param_overrides_for_graph_dict(graph_dict, log_path_str)
        rw_payload: dict[str, Any] = {"action": "run_workflow"}
        if deb_over:
            rw_payload["unit_param_overrides"] = deb_over
        initial_inputs = {
            "run_workflow": {
                "parser_output": {"run_workflow": rw_payload},
                "graph": graph_dict,
            },
        }

        async def _run_async() -> None:
            try:
                from runtime.run import run_workflow

                outputs = await asyncio.to_thread(
                    run_workflow,
                    run_workflow_graph_json,
                    initial_inputs=initial_inputs,
                    format="dict",
                )
                rw_out = (outputs.get("run_workflow") or {}) if isinstance(outputs, dict) else {}
                nested = rw_out.get("data") if isinstance(rw_out.get("data"), dict) else {}
                err = rw_out.get("error")
                _append_console("")
                _append_console("--- Outputs ---")
                _append_console(format_run_outputs(nested))
                if err and isinstance(err, str) and err.strip():
                    _append_console("")
                    _append_console("--- Error ---")
                    _append_console(f"  run_workflow: {err[:300]}")
                try:
                    from gui.chat.utils import collect_workflow_errors

                    errs = collect_workflow_errors(outputs)
                    if errs:
                        _append_console("")
                        _append_console("--- Errors ---")
                        for uid, err in errs:
                            _append_console(f"  {uid}: {err[:200]}")
                except Exception:
                    pass
                try:
                    log_path = log_path_str
                    grep_outputs = await asyncio.to_thread(
                        run_workflow,
                        grep_workflow_json,
                        initial_inputs={},
                        unit_param_overrides={"grep": {"source": log_path, "pattern": "."}},
                        format="dict",
                    )
                    g_out = (grep_outputs.get("grep") or {}) if isinstance(grep_outputs, dict) else {}
                    grep_text = g_out.get("out") if isinstance(g_out.get("out"), str) else ""
                    grep_err = g_out.get("error")
                    _append_console("")
                    _append_console("--- Log (grep) ---")
                    _append_console(grep_text if grep_text else "(no output)")
                    if grep_err and str(grep_err).strip():
                        _append_console(f"  grep error: {str(grep_err)[:200]}")
                except Exception as grep_ex:
                    _append_console("")
                    _append_console(f"--- Log (grep) --- Error: {grep_ex}")
            except Exception as e:
                _append_console("")
                _append_console(f"Error: {e}")

        page.run_task(_run_async)

    run_btn = ft.IconButton(
        icon=ft.Icons.PLAY_ARROW,
        tooltip="Run workflow (show console below)",
        on_click=_on_run_click,
    )

    def show_console_with_run_output(
        run_output: dict[str, Any],
        *,
        append_log_grep: bool = False,
    ) -> None:
        """Show the Workflow tab console and append run_output (e.g. from chat run_workflow). No re-run.
        If append_log_grep is True, also run the grep workflow on the debug log and append that section (same as Run button)."""
        _show_console()
        terminal_lines.clear()
        _append_console("Workflow run (from chat)")
        _append_console("")
        if isinstance(run_output.get("data"), dict) and "error" in run_output:
            nested = run_output["data"]
            err = run_output.get("error")
        else:
            nested = run_output if isinstance(run_output, dict) else {}
            err = None
        _append_console("--- Outputs ---")
        _append_console(format_run_outputs(nested))
        if isinstance(err, str) and err.strip():
            _append_console("")
            _append_console("--- Error ---")
            _append_console(f"  run_workflow: {err[:500]}")
        if append_log_grep:

            async def _append_log_grep() -> None:
                try:
                    from runtime.run import run_workflow

                    log_path = str(get_debug_log_path())
                    grep_outputs = await asyncio.to_thread(
                        run_workflow,
                        grep_workflow_json,
                        initial_inputs={},
                        unit_param_overrides={"grep": {"source": log_path, "pattern": "."}},
                        format="dict",
                    )
                    g_out = (grep_outputs.get("grep") or {}) if isinstance(grep_outputs, dict) else {}
                    grep_text = g_out.get("out") if isinstance(g_out.get("out"), str) else ""
                    grep_err = g_out.get("error")
                    _append_console("")
                    _append_console("--- Log (grep) ---")
                    _append_console(grep_text if grep_text else "(no output)")
                    if grep_err and str(grep_err).strip():
                        _append_console(f"  grep error: {str(grep_err)[:200]}")
                except Exception as grep_ex:
                    _append_console("")
                    _append_console(f"--- Log (grep) --- Error: {grep_ex}")
                try:
                    console_container.update()
                    page.update()
                except Exception:
                    pass

            page.run_task(_append_log_grep)
        try:
            console_container.update()
            page.update()
        except Exception:
            pass

    return WorkflowRunConsoleControls(
        console_container=console_container,
        run_button=run_btn,
        show_console_with_run_output=show_console_with_run_output,
    )
