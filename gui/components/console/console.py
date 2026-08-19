from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass

import flet as ft

from core.normalizer import to_process_graph
from core.schemas.process_graph import ProcessGraph
from gui.components.settings import (
    DEFAULT_CONSOLE_EXECUTION_TIMEOUT_S,
)
from gui.utils.code_editor import CODE_EDITOR_BG, build_code_display
from services.logging import setup_colored_logging

from .run_console import extract_keep_alive, format_run_outputs, run_via_jobs_and_await

logger = setup_colored_logging(logging.INFO)


@dataclass(frozen=True)
class WorkflowRunConsoleControls:
    """Console panel, toolbar Run control, and chat hook to mirror run output in the console."""

    console_container: ft.Container
    run_button: ft.IconButton
    show_console_with_run_output: Callable[..., None]

def build_workflow_run_console(
    page: ft.Page,
    graph_ref: list[ProcessGraph | None],
    show_toast: Callable[[ft.Page, str], object] | None,
    *,
    execution_timeout_s: float | None = DEFAULT_CONSOLE_EXECUTION_TIMEOUT_S,
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
        set_console_value(
            "\n".join(terminal_lines) if terminal_lines else _console_initial
        )

    def _show_console() -> None:
        if not console_visible[0]:
            console_visible[0] = True
            try:
                h = getattr(page, "window_height", None) or getattr(
                    getattr(page, "window", None), "height", None
                )
                console_container.height = (
                    int((h or 0) * CONSOLE_HEIGHT_FRACTION) or CONSOLE_HEIGHT_FALLBACK
                )
            except (AttributeError, TypeError, ValueError) as err:
                logger.debug("Failed to compute console_container.height: %s", err)
                console_container.height = CONSOLE_HEIGHT_FALLBACK

            try:
                console_container.update()
            except (RuntimeError, ValueError, TypeError) as err:
                logger.debug("Failed to update console_container: %s", err)

    # Accept object argument shape; flet handlers may pass different event objects.
    def _close_console(_e: object = None) -> None:
        console_visible[0] = False
        console_container.height = 0
        try:
            console_container.update()
            page.update()
        except (RuntimeError, ValueError, TypeError):
            pass

    console_close_btn = ft.IconButton(
        icon=ft.Icons.CLOSE,
        icon_size=18,
        tooltip="Close console",
        on_click=lambda e=None: _close_console(e),
        style=ft.ButtonStyle(padding=2),
    )

    # Build a border object robustly: try ft.border.Border.all, fallback to constructing Border manually.
    try:
        border_obj = ft.border.Border.all(1, ft.Colors.GREY_700)  # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError) as err:
        logger.debug("Failed to create border: %s", err)
        try:
            border_obj = ft.border.Border(
                left=ft.border.BorderSide(1, ft.Colors.GREY_700),
                top=ft.border.BorderSide(1, ft.Colors.GREY_700),
                right=ft.border.BorderSide(1, ft.Colors.GREY_700),
                bottom=ft.border.BorderSide(1, ft.Colors.GREY_700),
            )
        except (AttributeError, TypeError, ValueError):
            border_obj = None

    console_data_container = ft.Container(
        content=console_display_control,
        expand=True,
        border=border_obj,
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
                                ft.Text(
                                    "Console",
                                    size=12,
                                    weight=ft.FontWeight.W_500,
                                    color=ft.Colors.GREY_400,
                                ),
                                ft.Container(expand=True),
                                console_close_btn,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row([console_data_container], expand=True),
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

    # Handler accepts optional event and always returns None
    def _on_run_click(_e: object = None) -> None:
        graph = graph_ref[0]
        if graph is None:
            toast_fn = show_toast
            if toast_fn is not None:

                async def _no_graph() -> None:
                    maybe_coro = toast_fn(
                        page, "No workflow loaded. Open or create a workflow first."
                    )
                    if asyncio.iscoroutine(maybe_coro):
                        await maybe_coro

                _ = page.run_task(_no_graph)
            return

        _show_console()
        terminal_lines.clear()
        _append_console("Running workflow ...")


        async def _run_async() -> None:
            try:
                from agents.chat.graph_bridge import get_live_graph_dict

                live_graph = get_live_graph_dict()
                if live_graph is None:
                    _append_console("")
                    _append_console("Error: No live canvas graph available.")
                    return

                # Check whether the graph should run in long-lived mode.
                keep_alive = extract_keep_alive(live_graph)

                normalized_graph: ProcessGraph = to_process_graph(live_graph)

                outputs = await run_via_jobs_and_await(
                    workflow_graph=normalized_graph,
                    initial_inputs=None,
                    unit_param_overrides=None,
                    format="dict",
                    keep_alive=keep_alive,
                    timeout_s=execution_timeout_s,
                )
                outputs_value = outputs

                nested: dict[str, object] = {}
                err: str | None = None

                nested = outputs_value

                err_val = outputs_value.get("error")
                err = err_val if isinstance(err_val, str) else None

                _append_console("")
                _append_console("--- Outputs ---")
                _append_console(format_run_outputs(nested))

                if err:
                    _append_console("")
                    _append_console("--- Error ---")
                    _append_console(f"  run_workflow: {err[:300]}")

                try:
                    from agents.chat.utils import collect_workflow_errors

                    errs = collect_workflow_errors(outputs_value)
                    if errs:
                        _append_console("")
                        _append_console("--- Errors ---")
                        for uid, one_err in errs:
                            _append_console(f"  {uid}: {one_err[:200]}")
                except (ImportError, ModuleNotFoundError) as err2:
                    logger.debug("collect_workflow_errors import failed: %s", err2)
                except (TypeError, ValueError) as err2:
                    logger.debug("Failed to collect/format workflow errors: %s", err2)

            except (OSError, FileNotFoundError, PermissionError, TypeError, ValueError) as e2:
                _append_console("")
                _append_console(f"Error: {e2}")

            finally:
                try:
                    console_container.update()
                    page.update()
                except (RuntimeError, ValueError, TypeError):
                    pass


        _ = page.run_task(_run_async)


    run_btn = ft.IconButton(
        icon=ft.Icons.PLAY_ARROW,
        tooltip="Run workflow",
        on_click=lambda e=None: _on_run_click(e),
    )


    def show_console_with_run_output(
        run_output: dict[str, object],
    ) -> None:
        """Show the Workflow tab console and append run_output (e.g. from chat run_workflow). No re-run."""

        _show_console()
        terminal_lines.clear()
        _append_console("Workflow run (from chat)")
        _append_console("")

        nested = run_output
        err = run_output.get("error")

        nested_safe: dict[str, object] = nested

        _append_console("--- Outputs ---")
        _append_console(format_run_outputs(nested_safe))
        if isinstance(err, str) and err.strip():
            _append_console("")
            _append_console("--- Error ---")
            _append_console(f"  run_workflow: {err[:500]}")

        try:
            console_container.update()
            page.update()
        except (RuntimeError, ValueError, TypeError):
            pass

    return WorkflowRunConsoleControls(
        console_container=console_container,
        run_button=run_btn,
        show_console_with_run_output=show_console_with_run_output,
    )
