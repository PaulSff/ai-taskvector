from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

import flet as ft

from core.normalizer import to_process_graph
from core.schemas.process_graph import ProcessGraph
from gui.components.settings import DEFAULT_CONSOLE_EXECUTION_TIMEOUT_S
from gui.utils.code_editor import CODE_EDITOR_BG, build_code_display
from runtime.run import WorkflowTimeoutError
from services.logging import setup_colored_logging

from .run_console import (
    WorkflowRun,
    extract_keep_alive,
    format_run_outputs,
    run_via_jobs_and_await,
)

logger = setup_colored_logging(logging.INFO)


@dataclass(frozen=True)
class WorkflowRunConsoleControls:
    """Controls and callbacks for the workflow run console."""

    console_container: ft.Container
    run_button: ft.IconButton
    stop_button: ft.IconButton
    show_console_with_run_output: Callable[[dict[str, object]], None]


def build_workflow_run_console(
    page: ft.Page,
    graph_ref: list[ProcessGraph | None],
    show_toast: Callable[[ft.Page, str], object] | None,
    *,
    execution_timeout_s: float | None = DEFAULT_CONSOLE_EXECUTION_TIMEOUT_S,
) -> WorkflowRunConsoleControls:
    """Build the collapsible workflow console and wire its controls."""

    console_height_fraction = 0.36
    console_height_fallback = 200

    console_visible = False
    terminal_lines: list[str] = []

    active_run_task: asyncio.Task[object] | None = None
    active_workflow_run: WorkflowRun | None = None
    active_timer_task: asyncio.Task[object] | None = None
    stop_confirmation_event: asyncio.Event | None = None


    run_start_time: float | None = None
    run_state: str = "idle"


    console_initial_text = (
        "— Click Run to execute the workflow and see output. —"
    )

    (
        console_display_control,
        set_console_value,
        _,
    ) = build_code_display(
        console_initial_text,
        language="json",
        expand=True,
        page=page,
    )

    def append_console(text: str) -> None:
        terminal_lines.append(text)

        set_console_value(
            "\n".join(terminal_lines)
            if terminal_lines
            else console_initial_text
        )

    inline_status_text = ft.Text(
        "",
        size=11,
        color=ft.Colors.GREY_400,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
    )

    inline_status = ft.Container(
        content=inline_status_text,
        visible=False,
        padding=ft.padding.Padding.symmetric(horizontal=7, vertical=2),
        border_radius=8,
        bgcolor=ft.Colors.with_opacity(
            0.10,
            ft.Colors.GREY_400,
        ),
    )

    def set_inline_status(
        message: str | None,
        *,
        flush: bool = True,
    ) -> None:
        """Update the compact status indicator embedded in the console."""

        inline_status_text.value = message or ""
        inline_status.visible = bool(message and message.strip())

        if message:
            lowered = message.lower()

            if any(
                value in lowered
                for value in ("error", "failed", "timed out")
            ):
                inline_status_text.color = ft.Colors.RED_300
                inline_status.bgcolor = ft.Colors.with_opacity(
                    0.12,
                    ft.Colors.RED_400,
                )

            elif any(
                value in lowered
                for value in ("running", "stopping")
            ):
                inline_status_text.color = ft.Colors.AMBER_300
                inline_status.bgcolor = ft.Colors.with_opacity(
                    0.12,
                    ft.Colors.AMBER_400,
                )

            elif any(
                value in lowered
                for value in ("completed", "stopped")
            ):
                inline_status_text.color = ft.Colors.GREEN_300
                inline_status.bgcolor = ft.Colors.with_opacity(
                    0.12,
                    ft.Colors.GREEN_400,
                )

            else:
                inline_status_text.color = ft.Colors.GREY_400
                inline_status.bgcolor = ft.Colors.with_opacity(
                    0.10,
                    ft.Colors.GREY_400,
                )

        if flush:
            try:
                inline_status.update()
            except (RuntimeError, ValueError, TypeError) as exc:
                logger.debug("Failed to update inline status: %s", exc)

    def show_console() -> None:
        nonlocal console_visible

        if console_visible:
            return

        console_visible = True

        try:
            window_height = getattr(page, "window_height", None)

            if not window_height:
                window = getattr(page, "window", None)
                window_height = getattr(window, "height", None)

            console_container.height = (
                int((window_height or 0) * console_height_fraction)
                or console_height_fallback
            )

        except (AttributeError, TypeError, ValueError) as exc:
            logger.debug("Failed to calculate console height: %s", exc)
            console_container.height = console_height_fallback

        try:
            console_container.update()
        except (RuntimeError, ValueError, TypeError) as exc:
            logger.debug("Failed to show console: %s", exc)

    def close_console(_event: object = None) -> None:
        nonlocal console_visible

        console_visible = False
        console_container.height = 0

        try:
            console_container.update()
            page.update()
        except (RuntimeError, ValueError, TypeError) as exc:
            logger.debug("Failed to close console: %s", exc)

    def update_console() -> None:
        try:
            console_container.update()
            page.update()
        except (RuntimeError, ValueError, TypeError) as exc:
            logger.debug("Failed to update console: %s", exc)

    # --- timer ---
    timer_text = ft.Text(
        "",
        size=11,
        color=ft.Colors.GREY_600,
        max_lines=1,
    )

    console_timer = ft.Container(
        content=timer_text,
        padding=ft.padding.Padding.symmetric(horizontal=7, vertical=2),
    )


    def format_elapsed(seconds: float) -> str:
        seconds = max(0.0, seconds)
        total = int(seconds)
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    async def run_timer() -> None:
        nonlocal run_start_time
        while True:
            if run_start_time is None:
                return

            elapsed = asyncio.get_running_loop().time() - run_start_time
            timer_text.value = format_elapsed(elapsed)
            console_timer.update()

            await asyncio.sleep(0.25)


    def stop_timer() -> None:
        nonlocal active_timer_task, run_start_time
        if active_timer_task is not None and not active_timer_task.done():
            _ = active_timer_task.cancel()
        active_timer_task = None
        run_start_time = None
        timer_text.value = ""
        console_timer.update()


    def stop_active_run(_event: object = None) -> None:
        nonlocal run_state

        if run_state != "running":
            return

        if active_workflow_run is None:
            return

        run_state = "stopping"
        set_inline_status("Stopping...", flush=True)

        # Do not cancel active_run_task.
        # The WorkflowRun must stay alive while stop() publishes the stop
        # action and waits for workflow_status == "stopped".
        _ = page.run_task(stop_workflow_run)


    async def stop_workflow_run() -> None:
        run = active_workflow_run

        if run is None:
            return

        try:
            await run.stop()

        except (
            OSError,
            FileNotFoundError,
            PermissionError,
            TypeError,
            ValueError,
            RuntimeError,
        ) as exc:
            logger.exception("Failed to stop workflow")

            append_console("")
            append_console(f"Error stopping workflow: {exc}")
            set_inline_status("Failed to stop", flush=True)
            update_console()


    try:
        border_obj = ft.border.Border.all(
            1,
            ft.Colors.GREY_700,
        )

    except (AttributeError, TypeError, ValueError) as exc:
        logger.debug("Failed to create console border: %s", exc)

        try:
            border_obj = ft.border.Border(
                left=ft.border.BorderSide(
                    width=1,
                    color=ft.Colors.GREY_700,
                ),
                top=ft.border.BorderSide(
                    width=1,
                    color=ft.Colors.GREY_700,
                ),
                right=ft.border.BorderSide(
                    width=1,
                    color=ft.Colors.GREY_700,
                ),
                bottom=ft.border.BorderSide(
                    width=1,
                    color=ft.Colors.GREY_700,
                ),
            )

        except (AttributeError, TypeError, ValueError):
            border_obj = None

    console_close_button = ft.IconButton(
        icon=ft.Icons.CLOSE,
        icon_size=18,
        tooltip="Close console",
        on_click=close_console,
        style=ft.ButtonStyle(padding=2),
    )

    console_stop_button = ft.IconButton(
        icon=ft.Icons.STOP,
        icon_size=18,
        tooltip="Stop workflow",
        icon_color=ft.Colors.ORANGE_400,
        on_click=stop_active_run,
        style=ft.ButtonStyle(padding=2),
    )

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
                                inline_status,
                                console_timer,
                                ft.Container(expand=True),
                                console_stop_button,
                                console_close_button,
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
        animate=ft.Animation(
            duration=200,
            curve=ft.AnimationCurve.EASE_OUT,
        ),
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )

    async def show_no_graph_toast() -> None:
        if show_toast is None:
            return

        result = show_toast(
            page,
            "No workflow loaded. Open or create a workflow first.",
        )

        if asyncio.iscoroutine(result):
            await result


    async def render_result(outputs: dict[str, object]) -> None:
        nonlocal token_buffer, run_state

        if outputs.get("workflow_status") == "stopped":
            logger.info("Console: Workflow stop confirmed by runtime")

            run_state = "idle"
            set_inline_status("Stopped", flush=True)

            if stop_confirmation_event is not None:
                stop_confirmation_event.set()

            if show_toast is not None:
                result = show_toast(page, "Workflow stopped")

                if asyncio.iscoroutine(result):
                    await result

            append_console("")

            if token_buffer:
                append_console(token_buffer)
                token_buffer = ""

            append_console("Workflow stopped.")
            update_console()
            return


        if token_buffer:
            append_console(token_buffer)
            token_buffer = ""

        append_console("")
        append_console("--- Outputs (unit_id.port) ---")
        append_console(format_run_outputs(outputs))


    # buffering tokens as they arrive
    token_buffer = ""

    async def render_token(token: str) -> None:
        nonlocal token_buffer

        if not token:
            return

        token_buffer += token

        if "\n" in token_buffer:
            complete_lines = token_buffer.split("\n")
            token_buffer = complete_lines.pop()

            for line in complete_lines:
                append_console(line)

        set_console_value(
            "\n".join(terminal_lines + [token_buffer])
            if token_buffer
            else (
                "\n".join(terminal_lines)
                if terminal_lines
                else console_initial_text
            )
        )

        update_console()


    async def handle_error(error: str) -> None:
        append_console("")
        append_console("--- Workflow Error ---")
        append_console(f"  {error[:500]}")

        set_inline_status("Workflow error", flush=True)
        update_console()

    # run the current live workflow from console
    async def run_async() -> None:
        nonlocal active_run_task
        nonlocal active_workflow_run
        nonlocal active_timer_task
        nonlocal run_start_time
        nonlocal run_state
        nonlocal stop_confirmation_event

        stop_confirmation_event = asyncio.Event()

        try:
            from agents.chat.graph_bridge import get_live_graph_dict

            live_graph = get_live_graph_dict()

            if live_graph is None:
                append_console("")
                append_console("Error: No live canvas graph available.")
                set_inline_status("No live graph", flush=True)
                run_state = "idle"
                return

            keep_alive = extract_keep_alive(live_graph)
            normalized_graph = to_process_graph(live_graph)

            run_state = "running"

            set_inline_status(
                (
                    "Running — listening to the updates..."
                    if keep_alive
                    else "Running..."
                ),
                flush=True,
            )

            run_start_time = asyncio.get_running_loop().time()
            timer_text.value = "0:00"
            console_timer.update()

            active_timer_task = asyncio.create_task(run_timer())

            if keep_alive:
                active_workflow_run = WorkflowRun(
                    workflow_graph=normalized_graph,
                    initial_inputs=None,
                    unit_param_overrides=None,
                    format="dict",
                    keep_alive=True,
                    timeout_s=None,
                    on_result=render_result,
                )

                try:
                    _ = await active_workflow_run.wait()

                except asyncio.CancelledError:
                    # The run must be explicitly stopped before the task exits.
                    # Do not cancel active_run_task before calling stop().
                    await active_workflow_run.stop()
                    raise

            else:
                _ = await run_via_jobs_and_await(
                    workflow_graph=normalized_graph,
                    initial_inputs=None,
                    unit_param_overrides=None,
                    format="dict",
                    keep_alive=False,
                    timeout_s=execution_timeout_s,
                    on_result=render_result,
                    on_error=handle_error,
                    on_token=render_token,
                )

                if run_state == "running":
                    set_inline_status("Completed", flush=True)
                    run_state = "idle"

        except asyncio.CancelledError:
            run_state = "stopping"
            set_inline_status("Stopping...", flush=True)
            raise

        except WorkflowTimeoutError:
            append_console("")
            append_console("Error: Workflow timed out.")
            set_inline_status("Timed out", flush=True)
            run_state = "idle"

        except (
            ImportError,
            ModuleNotFoundError,
            OSError,
            FileNotFoundError,
            PermissionError,
            TypeError,
            ValueError,
            RuntimeError,
        ) as exc:
            logger.exception("Workflow console run failed")

            append_console("")
            append_console(f"Error: {exc}")
            set_inline_status("Failed", flush=True)
            run_state = "idle"

        finally:
            stop_timer()
            update_console()

            active_run_task = None
            active_workflow_run = None
            stop_confirmation_event = None



    def on_run_click(_event: object = None) -> None:
        nonlocal active_run_task, run_state

        if graph_ref[0] is None:
            _ = page.run_task(show_no_graph_toast)
            return

        # Reopen the console when Run is clicked during an existing run.
        show_console()

        if run_state != "idle":
            message = (
                "The workflow is stopping"
                if run_state == "stopping"
                else "The workflow is already running"
            )
            set_inline_status(message, flush=True)
            return

        if active_run_task is not None and not active_run_task.done():
            set_inline_status(
                "The workflow is already running",
                flush=True,
            )
            return

        terminal_lines.clear()
        append_console("Results:")
        set_inline_status("Running...", flush=True)

        run_state = "running"

        task = page.run_task(run_async)

        if isinstance(task, asyncio.Task):
            active_run_task = task

    run_button = ft.IconButton(
        icon=ft.Icons.PLAY_ARROW,
        tooltip="Run workflow",
        on_click=on_run_click,
    )

    def show_console_with_run_output(
        run_output: dict[str, object],
    ) -> None:
        """Display existing workflow output without executing the workflow."""

        show_console()

        terminal_lines.clear()
        append_console("Workflow run (from chat)")
        append_console("")
        append_console("--- Outputs (unit_id.port) ---")
        append_console(format_run_outputs(run_output))

        error_value = run_output.get("error")

        if isinstance(error_value, str) and error_value.strip():
            append_console("")
            append_console("--- Error ---")
            append_console(f"  run_workflow: {error_value[:500]}")

        update_console()

    return WorkflowRunConsoleControls(
        console_container=console_container,
        run_button=run_button,
        stop_button=console_stop_button,
        show_console_with_run_output=show_console_with_run_output,
    )
