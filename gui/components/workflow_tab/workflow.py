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

from gui.components.workflow_tab.console import build_workflow_run_console
from gui.components.workflow_tab.core_workflows import run_graph_diff, run_graph_summary
from gui.components.workflow_tab.dialogs import (
    open_add_link_dialog,
    open_add_node_dialog,
    open_export_workflow_dialog,
    open_import_workflow_dialog,
    open_remove_link_dialog,
    open_save_workflow_dialog,
    open_view_graph_code_dialog,
)
from gui.components.workflow_tab.dialogs.dialog_import_workflow import (
    NEW_FLOW_TEMPLATE_PATH,
    run_auto_import_workflow,
)
from gui.components.workflow_tab.editor.graph_code_editor import build_graph_code_view
from gui.components.workflow_tab.editor.graph_visual_editor import build_graph_canvas
from gui.utils.undo_redo import UndoRedoManager
from gui.components.settings import get_workflow_undo_max_depth


def build_workflow_tab(
    page: ft.Page,
    graph_ref: list[ProcessGraph | None],
    show_toast: Callable[[ft.Page, str], None],
    *,
    on_graph_changed: Callable[[ProcessGraph | None], None] | None = None,
    chat_graph_drag_group: str | None = None,
    chat_panel_api: dict[str, Any] | None = None,
) -> tuple[
    ft.Control,
    Callable[[ProcessGraph | None], None],
    Callable[[ProcessGraph | None], None],
    Callable[[], str | None],
    Callable[[], None],
    Callable[[], None],
    Callable[[dict[str, Any]], None],
]:
    """
    Build the Workflow tab content: toolbar + main area (graph or code view).
    graph_ref: mutable single-element list so dialogs/refresh can update the graph.
    show_toast: e.g. gui.utils.notifications.show_toast (async; signature (page, message)).
    Returns a ft.Column (expand=True) to use as contents[0].
    """
    def build_process_tab_content() -> ft.Control:
        # Always show the grid canvas; use empty graph when none loaded
        graph = graph_ref[0] if graph_ref[0] is not None else ProcessGraph()
        return build_graph_canvas(
            page,
            graph,
            on_right_click_link=lambda edge: (
                open_remove_link_dialog(page, graph_ref[0], on_graph_saved, suggested_link=edge)
                if graph_ref[0] is not None
                else None
            ),
            on_right_click_node=lambda uid: open_view_graph_code_dialog(
                page,
                graph_ref[0],
                unit_id=uid,
                on_graph_saved=on_graph_saved,
                chat_panel_api=chat_panel_api,
            ),
            on_right_click_comment=lambda cid: open_view_graph_code_dialog(
                page,
                graph_ref[0],
                comment_id=cid,
                on_graph_saved=on_graph_saved,
                chat_panel_api=chat_panel_api,
            ),
            on_node_drag_start=lambda _uid: on_graph_about_to_change("drag"),
            on_node_drag_end=lambda _uid: _drag_pushed.__setitem__(0, False),
            on_comment_drag_end=lambda _cid: _drag_pushed.__setitem__(0, False),
            chat_graph_drag_group=chat_graph_drag_group,
        )

    process_content = ft.Container(content=build_process_tab_content(), expand=True)

    def refresh_process_tab() -> None:
        process_content.content = build_process_tab_content()
        process_content.update()
        page.update()

    undo = UndoRedoManager(max_depth=get_workflow_undo_max_depth())
    view_mode: list[str] = ["graph"]  # "graph" | "code"
    _drag_pushed: list[bool] = [False]
    # Polls selection state in code view so the chat button can reflect "ready to send".
    # (The code editor wrapper does not provide a selection-changed callback.)
    selection_watch_token_ref: list[int] = [0]
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
        # Code tab keeps a separate JSON editor; rebuild it so assistant/canvas edits are not stale.
        if view_mode[0] == "code":
            code_view_container.content = build_code_view_content()
            try:
                code_view_container.update()
            except Exception:
                pass
        _update_undo_redo_buttons()
        if on_graph_changed is not None:
            try:
                on_graph_changed(new_graph)
            except Exception:
                pass

    def on_graph_saved(new_graph: ProcessGraph | None) -> None:
        # Record previous state for undo, then apply (new_graph may be None to clear)
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
        diff = run_graph_diff(prev, curr)
        return diff if diff else None

    def open_add_node(_e: ft.ControlEvent) -> None:
        try:
            summary = run_graph_summary(graph_ref[0])
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
        # Pass graph_ref so Save uses current graph at click time (not stale at dialog open).
        open_save_workflow_dialog(page, graph_ref)

    def remove_graph(_e: ft.ControlEvent) -> None:
        """Replace the current graph by importing new_flow_template.json via auto_import_workflow."""

        async def _run() -> None:
            if not NEW_FLOW_TEMPLATE_PATH.is_file():
                page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"Template not found: {NEW_FLOW_TEMPLATE_PATH}"),
                    open=True,
                )
                page.update()
                return
            try:
                raw = json.loads(NEW_FLOW_TEMPLATE_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                page.snack_bar = ft.SnackBar(content=ft.Text(f"Template load failed: {e}"), open=True)
                page.update()
                return
            canonical, err = await asyncio.to_thread(run_auto_import_workflow, raw)
            if err and err.strip():
                page.snack_bar = ft.SnackBar(content=ft.Text(err[:300]), open=True)
                page.update()
                return
            if canonical is None:
                page.snack_bar = ft.SnackBar(
                    content=ft.Text("Import failed (no graph returned)"),
                    open=True,
                )
                page.update()
                return
            try:
                graph = ProcessGraph.model_validate(canonical)
            except Exception as e:
                page.snack_bar = ft.SnackBar(content=ft.Text(str(e)), open=True)
                page.update()
                return
            on_graph_saved(graph)

        page.run_task(_run)

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

    def build_code_view_content() -> ft.Control:
        """Rebuild graph JSON editor for the code tab (position-mapped blocks, overlay, shortcuts)."""
        return build_graph_code_view(
            page,
            graph_ref,
            selection_watch_token_ref=selection_watch_token_ref,
            on_graph_saved=on_graph_saved,
            show_graph_view=show_graph_view,
            show_toast=show_toast,
            chat_panel_api=chat_panel_api,
        )

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

    _run_console = build_workflow_run_console(page, graph_ref, show_toast)
    console_container = _run_console.console_container
    run_btn = _run_console.run_button
    show_console_with_run_output = _run_console.show_console_with_run_output

    process_toolbar = ft.Container(
        content=ft.Row(
            [
                ft.IconButton(icon=ft.Icons.DOWNLOAD, tooltip="Import workflow", on_click=open_import_workflow),
                ft.IconButton(icon=ft.Icons.SAVE, tooltip="Save workflow", on_click=open_save_workflow),
                ft.IconButton(icon=ft.Icons.UPLOAD_FILE, tooltip="Export workflow", on_click=open_export_workflow),
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    tooltip="New workflow from template (auto-import)",
                    on_click=remove_graph,
                ),
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
    return process_tab_column, set_graph, apply_from_assistant, get_recent_changes, do_undo, do_redo, show_console_with_run_output
