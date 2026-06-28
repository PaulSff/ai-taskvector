from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import flet as ft

from agents.tools.workflow_path import get_tool_workflow_path
from core.schemas.process_graph import ProcessGraph
from gui.components.settings import get_debug_log_path
from gui.utils.code_editor import CODE_EDITOR_BG, build_code_display
from runtime import ZmqPublisher, ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics
from runtime.run import WorkflowTimeoutError

from .run_console import debug_log_param_overrides_for_graph_dict, format_run_outputs

JOB_PUB_ENDPOINT = "tcp://127.0.0.1:6630"
RESULT_SUB_ENDPOINT = "tcp://127.0.0.1:6640"
RESPONSE_PUB_ENDPOINT = RESULT_SUB_ENDPOINT  # response endpoint published to

DEFAULT_EXECUTION_TIMEOUT_S = 120.0


@dataclass(frozen=True)
class WorkflowRunConsoleControls:
    """Console panel, toolbar Run control, and chat hook to mirror run output in the console."""

    console_container: ft.Container
    run_button: ft.IconButton
    show_console_with_run_output: Callable[..., None]


def build_workflow_run_console(
    page: ft.Page,
    graph_ref: list[ProcessGraph | None],
    show_toast: Optional[Callable[[ft.Page, str], Any]],
    *,
    execution_timeout_s: float | None = DEFAULT_EXECUTION_TIMEOUT_S,
) -> WorkflowRunConsoleControls:
    """Build the collapsible console, wire Run, and return ``show_console_with_run_output`` for main/chat.

    Refactored: workflow runs via publishing jobs and awaiting ZMQ results (instead of direct run_workflow call).
    """

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
            except Exception:
                console_container.height = CONSOLE_HEIGHT_FALLBACK
            try:
                console_container.update()
            except Exception:
                pass

    # Accept any argument shape; flet handlers may pass different event objects.
    def _close_console(e: Any = None) -> None:
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
        on_click=lambda e=None: _close_console(e),
        style=ft.ButtonStyle(padding=2),
    )

    # Build a border object robustly: try ft.border.Border.all, fallback to constructing Border manually.
    try:
        border_obj = ft.border.Border.all(1, ft.Colors.GREY_700)  # type: ignore[attr-defined]
    except Exception:
        try:
            border_obj = ft.border.Border(
                left=ft.border.BorderSide(1, ft.Colors.GREY_700),
                top=ft.border.BorderSide(1, ft.Colors.GREY_700),
                right=ft.border.BorderSide(1, ft.Colors.GREY_700),
                bottom=ft.border.BorderSide(1, ft.Colors.GREY_700),
            )
        except Exception:
            border_obj = None  # type: ignore[assignment]

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

    run_workflow_graph_json = get_tool_workflow_path("run_workflow")
    grep_workflow_json = get_tool_workflow_path("grep")

    async def _run_via_jobs_and_await(
        *,
        workflow_path: str | Path,
        initial_inputs: dict[str, Any],
        unit_param_overrides: dict[str, dict[str, Any]] | None,
        format: str = "dict",
        timeout_s: float | None,
    ) -> Dict[str, Any]:
        run_id = uuid.uuid4().hex
        job_pub = ZmqPublisher(pub_endpoint=JOB_PUB_ENDPOINT, topics=ZmqTopics())
        topics = ZmqTopics()

        sub = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=RESULT_SUB_ENDPOINT,
                topics=(topics.token, topics.result, topics.error),
                accept_topics=None,
                rcvtimeo_ms=200,
            )
        )

        final_outputs: Optional[Dict[str, Any]] = None
        has_workflow_error = False
        workflow_error = ""

        async def _on_error(_topic: str, payload: dict[str, Any]) -> None:
            nonlocal has_workflow_error, workflow_error
            if payload.get("run_id") != run_id:
                return
            err = payload.get("error")
            workflow_error = err if isinstance(err, str) else str(err)
            has_workflow_error = True

        async def _on_result(_topic: str, payload: dict[str, Any]) -> None:
            nonlocal final_outputs
            if payload.get("run_id") != run_id:
                return
            outs = payload.get("outputs")
            if isinstance(outs, dict):
                final_outputs = outs

        async def _on_token(_topic: str, _payload: dict[str, Any]) -> None:
            return

        # token handler not needed for console panel; keep it wired anyway
        sub.on(topics.token, _on_token)
        sub.on(topics.result, _on_result)
        sub.on(topics.error, _on_error)

        start = time.monotonic()
        await asyncio.wait_for(sub.start(), timeout=30)

        job_pub.publish_job(
            run_id=run_id,
            workflow_path=str(workflow_path),  # <— ensure str for the publisher
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format=format,
            response_endpoint=RESPONSE_PUB_ENDPOINT,
        )

        try:
            while final_outputs is None and not has_workflow_error:
                if timeout_s is not None and (time.monotonic() - start) > timeout_s:
                    raise WorkflowTimeoutError(timeout_s)
                await asyncio.sleep(0.01)
        finally:
            await sub.stop()

        if has_workflow_error:
            raise RuntimeError(workflow_error)

        return final_outputs or {}

    # Handler accepts optional event and always returns None
    def _on_run_click(e: Any = None) -> None:
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

                page.run_task(_no_graph)
            return

        _show_console()
        terminal_lines.clear()
        _append_console("Running workflow ...")

        graph_dict = (
            graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else graph
        )
        log_path_str = str(get_debug_log_path())
        deb_over = debug_log_param_overrides_for_graph_dict(graph_dict, log_path_str)

        rw_payload: Dict[str, Any] = {"action": "run_workflow"}
        if deb_over:
            rw_payload["unit_param_overrides"] = deb_over

        initial_inputs: dict[str, Any] = {
            "run_workflow": {
                "parser_output": {"run_workflow": rw_payload},
                "graph": graph_dict,
            },
        }

        async def _run_async() -> None:
            try:
                # run_workflow (await job result)
                outputs = await _run_via_jobs_and_await(
                    workflow_path=run_workflow_graph_json,
                    initial_inputs=initial_inputs,
                    unit_param_overrides=deb_over,
                    format="dict",
                    timeout_s=execution_timeout_s,
                )

                rw_out = (
                    (outputs.get("run_workflow") or {})
                    if isinstance(outputs, dict)
                    else {}
                )
                nested = (
                    rw_out.get("data") if isinstance(rw_out.get("data"), dict) else {}
                )
                err = rw_out.get("error")

                _append_console("")
                _append_console("--- Outputs ---")
                nested_safe: Dict[str, Any] = nested if isinstance(nested, dict) else {}
                _append_console(format_run_outputs(nested_safe))

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
                        for uid, one_err in errs:
                            _append_console(f"  {uid}: {one_err[:200]}")
                except Exception:
                    pass

                # grep workflow (await job result)
                try:
                    grep_outputs = await _run_via_jobs_and_await(
                        workflow_path=grep_workflow_json,
                        initial_inputs={},
                        unit_param_overrides={
                            "grep": {"source": log_path_str, "pattern": "."}
                        },
                        format="dict",
                        timeout_s=execution_timeout_s,
                    )
                    g_out = (
                        (grep_outputs.get("grep") or {})
                        if isinstance(grep_outputs, dict)
                        else {}
                    )
                    grep_text = (
                        g_out.get("out") if isinstance(g_out.get("out"), str) else ""
                    )
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
            finally:
                try:
                    console_container.update()
                    page.update()
                except Exception:
                    pass

        page.run_task(_run_async)

    run_btn = ft.IconButton(
        icon=ft.Icons.PLAY_ARROW,
        tooltip="Run workflow (show console below)",
        on_click=lambda e=None: _on_run_click(e),
    )

    def show_console_with_run_output(
        run_output: Dict[str, Any],
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

        nested_safe: Dict[str, Any] = nested if isinstance(nested, dict) else {}
        _append_console("--- Outputs ---")
        _append_console(format_run_outputs(nested_safe))
        if isinstance(err, str) and err.strip():
            _append_console("")
            _append_console("--- Error ---")
            _append_console(f"  run_workflow: {err[:500]}")

        if append_log_grep:

            async def _append_log_grep() -> None:
                try:
                    grep_outputs = await _run_via_jobs_and_await(
                        workflow_path=grep_workflow_json,
                        initial_inputs={},
                        unit_param_overrides={
                            "grep": {
                                "source": str(get_debug_log_path()),
                                "pattern": ".",
                            }
                        },
                        format="dict",
                        timeout_s=execution_timeout_s,
                    )
                    g_out = (
                        (grep_outputs.get("grep") or {})
                        if isinstance(grep_outputs, dict)
                        else {}
                    )
                    grep_text = (
                        g_out.get("out") if isinstance(g_out.get("out"), str) else ""
                    )
                    grep_err = g_out.get("error")

                    _append_console("")
                    _append_console("--- Log (grep) ---")
                    _append_console(grep_text if grep_text else "(no output)")
                    if grep_err and str(grep_err).strip():
                        _append_console(f"  grep error: {str(grep_err)[:200]}")

                except Exception as grep_ex:
                    _append_console("")
                    _append_console(f"--- Log (grep) --- Error: {grep_ex}")
                finally:
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
