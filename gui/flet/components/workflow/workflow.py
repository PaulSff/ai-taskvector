"""
Workflow tab UI: process graph (canvas), graph/code view toggle, toolbar, dialogs.
Run button runs the current graph via the one-unit run_workflow workflow and shows output in a bottom console (1/4 height, on click).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

import flet as ft

from core.schemas.process_graph import ProcessGraph

from gui.flet.components.workflow.run_console import (
    format_run_outputs,
)
from gui.flet.components.workflow.dialogs import (
    dict_to_graph,
    open_add_link_dialog,
    open_add_node_dialog,
    open_export_workflow_dialog,
    open_import_workflow_dialog,
    open_remove_link_dialog,
    open_save_workflow_dialog,
    open_view_graph_code_dialog,
)
from gui.flet.components.workflow.graph_canvas import build_graph_canvas
from gui.flet.tools.code_editor import build_code_editor
from gui.flet.tools.keyboard_commands import create_keyboard_handler
from gui.flet.tools.undo_redo import UndoRedoManager

from core.graph import graph_diff, graph_summary


def build_workflow_tab(
    page: ft.Page,
    graph_ref: list[ProcessGraph | None],
    show_toast: Callable[[ft.Page, str], None],
    *,
    on_graph_changed: Callable[[ProcessGraph | None], None] | None = None,
) -> tuple[
    ft.Control,
    Callable[[ProcessGraph | None], None],
    Callable[[ProcessGraph | None], None],
    Callable[[], str | None],
    Callable[[], None],
    Callable[[], None],
]:
    """
    Build the Workflow tab content: toolbar + main area (graph or code view).
    graph_ref: mutable single-element list so dialogs/refresh can update the graph.
    show_toast: e.g. gui.flet.tools.notifications.show_toast (async; signature (page, message)).
    Returns a ft.Column (expand=True) to use as contents[0].
    """
    def build_process_tab_content() -> ft.Control:
        if graph_ref[0] is not None:
            return build_graph_canvas(
                page,
                graph_ref[0],
                on_right_click_link=lambda edge: (
                    open_remove_link_dialog(page, graph_ref[0], on_graph_saved, suggested_link=edge)
                    if graph_ref[0] is not None
                    else None
                ),
                on_right_click_node=lambda uid: open_view_graph_code_dialog(
                    page, graph_ref[0], unit_id=uid, on_graph_saved=on_graph_saved
                ),
                on_node_drag_start=lambda _uid: on_graph_about_to_change("drag"),
                on_node_drag_end=lambda _uid: _drag_pushed.__setitem__(0, False),
            )
        return ft.Column(
            [
                ft.Text("Process graph", size=20, weight=ft.FontWeight.BOLD),
                ft.Text("No process graph loaded. Click + to add a node or load from file."),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    process_content = ft.Container(content=build_process_tab_content(), expand=True)

    def refresh_process_tab() -> None:
        process_content.content = build_process_tab_content()
        process_content.update()
        page.update()

    undo = UndoRedoManager(max_depth=50)
    view_mode: list[str] = ["graph"]  # "graph" | "code"
    _drag_pushed: list[bool] = [False]
    undo_btn_ref: list[ft.IconButton | None] = [None]
    redo_btn_ref: list[ft.IconButton | None] = [None]

    ACTIVE_TOOLBAR_ICON_COLOR = ft.Colors.GREY_200
    INACTIVE_TOOLBAR_ICON_COLOR = ft.Colors.GREY_600

    def _update_undo_redo_buttons() -> None:
        ub = undo_btn_ref[0]
        rb = redo_btn_ref[0]
        if ub is None or rb is None:
            return
        enabled = view_mode[0] == "graph"
        ub.disabled = (not enabled) or (not undo.can_undo())
        rb.disabled = (not enabled) or (not undo.can_redo())
        ub.icon_color = ACTIVE_TOOLBAR_ICON_COLOR if not ub.disabled else INACTIVE_TOOLBAR_ICON_COLOR
        rb.icon_color = ACTIVE_TOOLBAR_ICON_COLOR if not rb.disabled else INACTIVE_TOOLBAR_ICON_COLOR
        try:
            ub.update()
            rb.update()
        except Exception:
            pass

    def on_graph_about_to_change(_reason: str) -> None:
        """Push undo snapshot once per continuous operation (e.g. drag)."""
        if graph_ref[0] is None:
            return
        if _drag_pushed[0] and _reason == "drag":
            return
        undo.push_undo(graph_ref[0])
        if _reason == "drag":
            _drag_pushed[0] = True
        _update_undo_redo_buttons()

    def set_graph(new_graph: ProcessGraph | None) -> None:
        """Set graph_ref[0] and refresh the canvas/code views."""
        graph_ref[0] = new_graph
        refresh_process_tab()
        _update_undo_redo_buttons()
        if on_graph_changed is not None:
            try:
                on_graph_changed(new_graph)
            except Exception:
                pass

    def on_graph_saved(new_graph: ProcessGraph) -> None:
        # Record previous state for undo, then apply
        if graph_ref[0] is not None:
            undo.push_undo(graph_ref[0])
        else:
            undo.push_undo(None)
        _drag_pushed[0] = False
        set_graph(new_graph)
        _update_undo_redo_buttons()

    def do_undo() -> None:
        if view_mode[0] != "graph" or not undo.can_undo():
            return
        try:
            restored = undo.undo(graph_ref[0])
        except IndexError:
            return
        _drag_pushed[0] = False
        set_graph(restored)
        _update_undo_redo_buttons()

    def do_redo() -> None:
        if view_mode[0] != "graph" or not undo.can_redo():
            return
        try:
            restored = undo.redo(graph_ref[0])
        except IndexError:
            return
        _drag_pushed[0] = False
        set_graph(restored)
        _update_undo_redo_buttons()

    def apply_from_assistant(new_graph: ProcessGraph | None) -> None:
        """Apply graph from assistant edits and push undo so future diffs work."""
        if graph_ref[0] is not None:
            undo.push_undo(graph_ref[0])
        else:
            undo.push_undo(None)
        _drag_pushed[0] = False
        set_graph(new_graph)
        _update_undo_redo_buttons()

    def get_recent_changes() -> str | None:
        """Diff between previous snapshot and current graph. Returns None if no undo history."""
        prev = undo.get_previous_snapshot()
        curr = graph_ref[0]
        if prev is None or curr is None:
            return None
        prev_graph = ProcessGraph.model_validate(prev)
        diff = graph_diff(prev_graph, curr)
        return diff if diff else None

    def build_code_view_content() -> ft.Control:
        """Build the inline code view (JSON editor + Back to graph / Apply)."""
        try:
            json_str = (
                json.dumps(graph_ref[0].model_dump(by_alias=True), indent=2)
                if graph_ref[0] is not None
                else "{}"
            )
        except Exception:
            json_str = "{}"

        code_editor_control, get_value, show_find_bar, hide_find_bar = build_code_editor(
            json_str, expand=True, page=page
        )

        _prev_keyboard = getattr(page, "on_keyboard_event", None)
        page.on_keyboard_event = create_keyboard_handler(
            _prev_keyboard,
            on_find=show_find_bar,
            on_escape=hide_find_bar,
        )

        def back_to_graph(_e: ft.ControlEvent) -> None:
            page.on_keyboard_event = _prev_keyboard
            show_graph_view()

        def apply_code(_e: ft.ControlEvent) -> None:
            try:
                text = get_value()
                data = json.loads(text)
                new_graph = dict_to_graph(data)
            except Exception as ex:
                page.snack_bar = ft.SnackBar(content=ft.Text(str(ex)), open=True)
                page.update()
                return
            on_graph_saved(new_graph)
            show_graph_view()

        async def copy_to_clipboard(_e: ft.ControlEvent) -> None:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                await page.clipboard.set(get_value())
            await show_toast(page, "Copied!")

        return ft.Column(
            [
                ft.Container(
                    content=ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.ARROW_BACK,
                                tooltip="Back to graph",
                                on_click=back_to_graph,
                                icon_color=ft.Colors.PRIMARY,
                            ),
                            ft.TextButton(content="Apply", on_click=apply_code),
                            ft.Container(expand=True),
                            ft.IconButton(
                                icon=ft.Icons.COPY,
                                tooltip="Copy to clipboard",
                                on_click=copy_to_clipboard,
                                icon_color=ft.Colors.PRIMARY,
                            ),
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

    def open_add_node(_e: ft.ControlEvent) -> None:
        try:
            summary = graph_summary(graph_ref[0]) if graph_ref[0] is not None else {"units": [], "connections": []}
            open_add_node_dialog(page, summary, graph_ref[0], on_graph_saved)
        except Exception as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(str(ex)), open=True)
            page.update()

    def open_link(_e: ft.ControlEvent) -> None:
        if graph_ref[0] is None:
            return
        try:
            open_add_link_dialog(page, graph_ref[0], on_graph_saved)
        except Exception as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(str(ex)), open=True)
            page.update()

    def open_import_workflow(_e: ft.ControlEvent) -> None:
        try:
            open_import_workflow_dialog(page, on_graph_saved)
        except Exception as ex:
            import traceback
            msg = traceback.format_exc()
            page.snack_bar = ft.SnackBar(
                content=ft.Text(str(ex)[:200], max_lines=5),
                open=True,
            )
            page.update()
            print("Import workflow dialog error:", msg)

    def open_save_workflow(_e: ft.ControlEvent) -> None:
        # Opens a versioned save dialog (timestamped filename; skips if no changes).
        open_save_workflow_dialog(page, graph_ref[0])

    def open_export_workflow(_e: ft.ControlEvent) -> None:
        open_export_workflow_dialog(page, graph_ref[0])

    code_view_container = ft.Container(
        expand=True,
        content=ft.Text("Code", color=ft.Colors.GREY_500),
        bgcolor=ft.Colors.TRANSPARENT,
    )
    process_main_view = ft.Container(expand=True, content=process_content)

    ACTIVE_ICON_COLOR = ft.Colors.GREY_200
    INACTIVE_ICON_COLOR = ft.Colors.GREY_500

    def update_view_tab_icons(active: str) -> None:
        """Set icon color for Graph/Code tab buttons; active='graph' or 'code'."""
        graph_btn.icon_color = ACTIVE_ICON_COLOR if active == "graph" else INACTIVE_ICON_COLOR
        code_btn.icon_color = ACTIVE_ICON_COLOR if active == "code" else INACTIVE_ICON_COLOR
        graph_btn.update()
        code_btn.update()

    def show_graph_view() -> None:
        view_mode[0] = "graph"
        process_main_view.content = process_content
        refresh_process_tab()
        update_view_tab_icons("graph")
        _update_undo_redo_buttons()
        process_main_view.update()
        page.update()

    def show_code_view_switch(_e: ft.ControlEvent) -> None:
        view_mode[0] = "code"
        code_view_container.content = build_code_view_content()
        process_main_view.content = code_view_container
        update_view_tab_icons("code")
        _update_undo_redo_buttons()
        process_main_view.update()
        page.update()

    def show_graph_view_switch(_e: ft.ControlEvent) -> None:
        show_graph_view()

    graph_btn = ft.IconButton(
        icon=ft.Icons.ACCOUNT_TREE,
        tooltip="Graph",
        on_click=show_graph_view_switch,
        icon_color=ACTIVE_ICON_COLOR,
    )
    code_btn = ft.IconButton(
        icon=ft.Icons.CODE,
        tooltip="Code",
        on_click=show_code_view_switch,
        icon_color=INACTIVE_ICON_COLOR,
    )

    def _on_toolbar_undo(_e: ft.ControlEvent) -> None:
        do_undo()

    def _on_toolbar_redo(_e: ft.ControlEvent) -> None:
        do_redo()

    undo_btn = ft.IconButton(
        icon=ft.Icons.UNDO,
        tooltip="Undo",
        on_click=_on_toolbar_undo,
        icon_color=ACTIVE_TOOLBAR_ICON_COLOR,
        disabled=True,
    )
    redo_btn = ft.IconButton(
        icon=ft.Icons.REDO,
        tooltip="Redo",
        on_click=_on_toolbar_redo,
        icon_color=ACTIVE_TOOLBAR_ICON_COLOR,
        disabled=True,
    )
    undo_btn_ref[0] = undo_btn
    redo_btn_ref[0] = redo_btn
    _update_undo_redo_buttons()

    # Bottom console (1/3 screen height), shown on Run click
    CONSOLE_HEIGHT_FRACTION = 0.36
    CONSOLE_HEIGHT_FALLBACK = 200
    console_visible: list[bool] = [False]
    terminal_lines: list[str] = []
    terminal_text = ft.Text(
        value="— Click Run to execute the workflow and see output. —",
        selectable=True,
        font_family="monospace",
        size=12,
        no_wrap=False,
        overflow=ft.TextOverflow.VISIBLE,
    )

    def _append_console(text: str) -> None:
        terminal_lines.append(text)
        terminal_text.value = "\n".join(terminal_lines) if terminal_lines else ""
        try:
            terminal_text.update()
        except Exception:
            pass

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
        content=terminal_text,
        expand=True,
        border=ft.border.all(1, ft.Colors.GREY_700),
        border_radius=4,
        padding=6,
        bgcolor=ft.Colors.GREY_900,
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

    _RUN_WORKFLOW_JSON = Path(__file__).resolve().parent / "run_workflow.json"
    _GREP_JSON = Path(__file__).resolve().parent / "grep.json"

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
        initial_inputs = {
            "run_workflow": {
                "parser_output": {"run_workflow": {"action": "run_workflow"}},
                "graph": graph_dict,
            },
        }

        async def _run_async() -> None:
            try:
                from runtime.run import run_workflow
                outputs = await asyncio.to_thread(
                    run_workflow,
                    _RUN_WORKFLOW_JSON,
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
                    from gui.flet.chat_with_the_assistants.workflow_designer_handler import collect_workflow_errors
                    errs = collect_workflow_errors(outputs)
                    if errs:
                        _append_console("")
                        _append_console("--- Errors ---")
                        for uid, err in errs:
                            _append_console(f"  {uid}: {err[:200]}")
                except Exception:
                    pass
                # Grep the debug log (path from GUI settings); no pattern filter — show all lines
                try:
                    from gui.flet.components.settings import get_debug_log_path
                    log_path = str(get_debug_log_path())
                    grep_outputs = await asyncio.to_thread(
                        run_workflow,
                        _GREP_JSON,
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

    process_toolbar = ft.Container(
        content=ft.Row(
            [
                ft.IconButton(icon=ft.Icons.DOWNLOAD, tooltip="Import workflow", on_click=open_import_workflow),
                ft.IconButton(icon=ft.Icons.SAVE, tooltip="Save workflow", on_click=open_save_workflow),
                ft.IconButton(icon=ft.Icons.UPLOAD_FILE, tooltip="Export to Node-RED / PyFlow / n8n", on_click=open_export_workflow),
                ft.IconButton(icon=ft.Icons.ADD, tooltip="Add node", on_click=open_add_node),
                ft.IconButton(icon=ft.Icons.LINK, tooltip="Add link", on_click=open_link),
                undo_btn,
                redo_btn,
                run_btn,
                ft.Container(expand=True),  # spacer
                graph_btn,
                code_btn,
            ],
            spacing=4,
        ),
        bgcolor=ft.Colors.GREY_900,
        padding=8,
    )
    process_tab_column = ft.Column(
        [
            process_toolbar,
            process_main_view,
            console_container,
        ],
        expand=True,
        spacing=0,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    return process_tab_column, set_graph, apply_from_assistant, get_recent_changes, do_undo, do_redo
