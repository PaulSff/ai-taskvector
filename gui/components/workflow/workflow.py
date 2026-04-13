"""
Workflow tab UI: process graph (canvas), graph/code view toggle, toolbar, dialogs.
Run button runs the current graph via the one-unit run_workflow workflow and shows output in a bottom console (1/4 height, on click).
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Callable

import flet as ft

from assistants.tools.workflow_path import get_tool_workflow_path
from core.schemas.process_graph import ProcessGraph

from gui.components.workflow.core_workflows import run_graph_diff, run_graph_summary
from gui.components.workflow.run_console import (
    debug_log_param_overrides_for_graph_dict,
    format_run_outputs,
)
from gui.components.workflow.dialogs import (
    dict_to_graph,
    open_add_link_dialog,
    open_add_node_dialog,
    open_export_workflow_dialog,
    open_import_workflow_dialog,
    open_remove_link_dialog,
    open_save_workflow_dialog,
    open_view_graph_code_dialog,
)
from gui.components.workflow.dialogs.dialog_import_workflow import (
    NEW_FLOW_TEMPLATE_PATH,
    run_auto_import_workflow,
)
from gui.components.workflow.graph_canvas import build_graph_canvas
from gui.components.workflow.overlay_editor import (
    create_graph_json_overlay,
    get_block_index_from_cursor,
)
from gui.utils.code_editor import (
    CODE_EDITOR_BG,
    build_code_display,
    build_code_editor,
    format_json_for_editor,
)
from gui.utils.keyboard_commands import create_keyboard_handler
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

    def build_code_view_content() -> ft.Control:
        """Production version: position-mapped code block editing."""

        try:
            raw_payload = graph_ref[0].model_dump(by_alias=True) if graph_ref[0] else {}
        except Exception:
            raw_payload = {}

        full_json_ref = [raw_payload]
        block_ranges_ref = [[]]

        # -------------------------
        # JSON formatter + position map
        # -------------------------
        def format_json_with_block_map(data: dict):
            import json

            parts: list[str] = []
            block_ranges: list[tuple[int, int, Any]] = []
            cursor = 0

            def add(txt: str):
                nonlocal cursor
                parts.append(txt)
                cursor += len(txt)

            def indent_lines(text: str, spaces: int) -> str:
                pad = " " * spaces
                return "\n".join(pad + line if line else line for line in text.splitlines())

            add("{\n")

            items = list(data.items())

            for i, (key, value) in enumerate(items):
                is_last_key = i == len(items) - 1

                # -------------------------
                # Special handling: code_blocks
                # -------------------------
                if key == "code_blocks" and isinstance(value, list):
                    add(f'  "{key}": [\n')

                    for j, block in enumerate(value):
                        is_last_block = j == len(value) - 1

                        block_str = json.dumps(block, indent=2, ensure_ascii=False)
                        block_str = indent_lines(block_str, 4)

                        start = cursor
                        add(block_str)
                        end = cursor

                        block_ranges.append((start, end, ("code_blocks", j)))

                        if not is_last_block:
                            add(",\n")
                        else:
                            add("\n")

                    add("  ]")

                # -------------------------
                # comments (per-sticker info → Cmd+E overlay, same idea as dialog_view_graph_code)
                # -------------------------
                elif key == "comments" and isinstance(value, list):
                    add(f'  "{key}": [\n')

                    for j, c in enumerate(value):
                        is_last_c = j == len(value) - 1

                        raw = json.dumps(c, indent=2, ensure_ascii=False)
                        block_str = indent_lines(raw, 4)

                        start = cursor
                        add(block_str)
                        end = cursor

                        if (
                            isinstance(c, dict)
                            and "info" in c
                            and isinstance(c.get("id", ""), str)
                            and c.get("id", "").startswith("comment_")
                        ):
                            try:
                                info_repr = json.dumps(c.get("info", ""), ensure_ascii=False)
                                key_idx = block_str.find('"info":')
                                val_idx = (
                                    block_str.find(info_repr, key_idx) if key_idx != -1 else -1
                                )
                                if val_idx != -1:
                                    block_ranges.append(
                                        (
                                            start + val_idx,
                                            start + val_idx + len(info_repr),
                                            ("comment_info", c.get("id")),
                                        )
                                    )
                                else:
                                    block_ranges.append(
                                        (start, end, ("comment_obj", c.get("id")))
                                    )
                            except Exception:
                                block_ranges.append(
                                    (start, end, ("comment_obj", c.get("id")))
                                )

                        if not is_last_c:
                            add(",\n")
                        else:
                            add("\n")

                    add("  ]")

                # -------------------------
                # Single nested comment object as a property value
                # -------------------------
                elif (
                    isinstance(value, dict)
                    and "info" in value
                    and isinstance(value.get("id", ""), str)
                    and value.get("id", "").startswith("comment_")
                ):
                    value_str = json.dumps(value, indent=2, ensure_ascii=False)
                    value_lines = [l for l in value_str.splitlines() if l.strip() != ""]
                    value_str = "\n".join(value_lines)
                    value_str = indent_lines(value_str, 2).strip()
                    fragment = f'  "{key}": {value_str}'

                    start = cursor
                    add(fragment)
                    end = cursor

                    try:
                        info_repr = json.dumps(value.get("info", ""), ensure_ascii=False)
                        key_idx = fragment.find('"info":')
                        val_idx = fragment.find(info_repr, key_idx) if key_idx != -1 else -1
                        if val_idx != -1:
                            block_ranges.append(
                                (
                                    start + val_idx,
                                    start + val_idx + len(info_repr),
                                    ("comment_info", value.get("id")),
                                )
                            )
                        else:
                            block_ranges.append(
                                (start, end, ("comment_obj", value.get("id")))
                            )
                    except Exception:
                        block_ranges.append(
                            (start, end, ("comment_obj", value.get("id")))
                        )

                # -------------------------
                # Normal keys
                # -------------------------
                else:
                    value_str = json.dumps(value, indent=2, ensure_ascii=False)

                    # Normalize (remove accidental blank lines)
                    value_lines = [l for l in value_str.splitlines() if l.strip() != ""]
                    value_str = "\n".join(value_lines)

                    value_str = indent_lines(value_str, 2)

                    add(f'  "{key}": {value_str.strip()}')

                # -------------------------
                # Key separator
                # -------------------------
                if not is_last_key:
                    add(",\n")
                else:
                    add("\n")

            add("}")

            # -------------------------
            # Final normalization pass (safety net)
            # -------------------------
            final = "".join(parts)
            final = "\n".join(line for line in final.splitlines() if line.strip() != "")

            return final, block_ranges

        # -------------------------
        # Editor builder
        # -------------------------
        def build_editor_from_state():
            formatted, ranges = format_json_with_block_map(full_json_ref[0])
            block_ranges_ref[0] = ranges

            return build_code_editor(
                code=formatted,
                expand=True,
                page=page,
                language="json",
            )

        (
            code_editor_control,
            get_value,
            show_find_bar,
            hide_find_bar,
            get_selection_range,
            set_editor_selection,
        ) = build_editor_from_state()

        editor_container = ft.Container(code_editor_control, expand=True)

        def refresh_editor():
            nonlocal get_value, show_find_bar, hide_find_bar, get_selection_range, set_editor_selection
            (
                new_editor,
                get_value,
                show_find_bar,
                hide_find_bar,
                get_selection_range,
                set_editor_selection,
            ) = build_editor_from_state()
            editor_container.content = new_editor
            editor_container.update()

        _overlay = create_graph_json_overlay(
            page,
            full_json_ref=full_json_ref,
            refresh_editor=refresh_editor,
            editor_container=editor_container,
            graph=None,
            hide_editor_when_overlay=False,
        )
        code_overlay = _overlay.code_overlay
        active_editor = _overlay.active_editor
        close_overlay = _overlay.close_overlay
        open_code_editor = _overlay.open_code_editor

        # -------------------------
        # Hint UI
        # -------------------------
        hint_container = ft.Container(
            content=ft.Text(
                "Use Cmd+E to edit the code",
                size=12,
                color=ft.Colors.GREY_400,
            ),
            visible=False,
            right=20,
            bottom=20,
        )

        # -------------------------
        # Keyboard shortcut
        # -------------------------
        def trigger_edit_code_block():
            """Open the code editor for the block under the cursor, if any."""
            idx = get_block_index_from_cursor(
                get_selection_range, block_ranges_ref[0], active_editor
            )
            if idx is not None:
                open_code_editor(idx)

        page.on_keyboard_event = create_keyboard_handler(
            chain_to=page.on_keyboard_event,      # keep previous chain
            on_find=show_find_bar,                # existing find bar shortcut
            on_escape=hide_find_bar,              # existing escape shortcut
            on_edit_code_block=trigger_edit_code_block,  # new Cmd/Ctrl+E
        )
        

        # -------------------------
        # Chat share selection 
        # -------------------------
        CHAT_ICON_INACTIVE_COLOR = ft.Colors.PRIMARY
        CHAT_ICON_ACTIVE_COLOR = ft.Colors.GREEN_500
        chat_icon_btn_ref = [None]

        this_watch_token = selection_watch_token_ref[0] + 1
        selection_watch_token_ref[0] = this_watch_token

        async def _add_selection_to_chat(_e):
            api = chat_panel_api or {}
            fn = api.get("add_code_reference")
            if not callable(fn):
                await show_toast(page, "Chat not ready")
                return

            rng = get_selection_range()
            if not rng:
                await show_toast(page, "Select something first")
                return

            a, b = rng
            if a > b:
                a, b = b, a

            txt = get_value() or ""
            a = max(0, min(len(txt), a))
            b = max(0, min(len(txt), b))

            if a >= b:
                await show_toast(page, "Select something first")
                return

            snippet = txt[a:b]
            if not snippet.strip():
                await show_toast(page, "Select something first")
                return

            fn(snippet=snippet, start=a, end=b)

        async def _watch_selection():
            await asyncio.sleep(0.05)
            last = None

            while selection_watch_token_ref[0] == this_watch_token:
                try:
                    rng = get_selection_range()
                    has = False

                    if rng:
                        a, b = sorted(rng)
                        txt = get_value() or ""
                        if a < b and txt[a:b].strip():
                            has = True

                    if last != has:
                        btn = chat_icon_btn_ref[0]
                        if btn:
                            btn.icon_color = (
                                CHAT_ICON_ACTIVE_COLOR if has else CHAT_ICON_INACTIVE_COLOR
                            )
                            btn.update()
                        last = has

                except Exception:
                    pass

                await asyncio.sleep(0.25)

        async def _watch_cursor():
            await asyncio.sleep(0.05)
            last_inside = None

            while selection_watch_token_ref[0] == this_watch_token:
                try:
                    idx = get_block_index_from_cursor(
                        get_selection_range, block_ranges_ref[0], active_editor
                    )
                    inside = idx is not None

                    if inside != last_inside:
                        hint_container.visible = inside
                        hint_container.update()
                        last_inside = inside

                except Exception:
                    pass

                await asyncio.sleep(0.2)

        chat_icon_btn = ft.IconButton(
            icon=ft.Icons.CHAT_BUBBLE_OUTLINE,
            on_click=lambda e: page.run_task(_add_selection_to_chat, e),
            icon_color=CHAT_ICON_INACTIVE_COLOR,
        )
        chat_icon_btn_ref[0] = chat_icon_btn

        # -------------------------
        # Toolbar
        # -------------------------
        async def copy_to_clipboard(_e):
            await page.clipboard.set(get_value() or "")
            await show_toast(page, "Copied!")

        def scroll_to_todo_list(_e):
            if code_overlay.visible:
                close_overlay()
            text = get_value() or ""
            m = re.search(r'^\s*"todo_list"\s*:', text, re.MULTILINE)
            if not m:
                m = re.search(r'"todo_list"\s*:', text)
            if not m:
                page.snack_bar = ft.SnackBar(
                    content=ft.Text("No todo_list in this graph"),
                    open=True,
                )
                page.update()
                return
            set_editor_selection(m.start(), m.end())

        def apply_code(_e):
            try:
                data = json.loads(get_value())
                full_json_ref[0] = data
                on_graph_saved(dict_to_graph(data))
                show_graph_view()
            except Exception as ex:
                page.snack_bar = ft.SnackBar(content=ft.Text(str(ex)), open=True)
                page.update()

        def back_to_graph(_e):
            selection_watch_token_ref[0] += 1
            show_graph_view()

        toolbar = ft.Row(
            [
                ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=back_to_graph),
                ft.TextButton("Apply", on_click=apply_code),
                ft.Container(expand=True),
                ft.IconButton(
                    icon=ft.Icons.FORMAT_LIST_BULLETED,
                    tooltip="Scroll to todo list",
                    on_click=scroll_to_todo_list,
                    icon_color=ft.Colors.PRIMARY,
                ),
                ft.IconButton(icon=ft.Icons.COPY, on_click=copy_to_clipboard),
                chat_icon_btn,
            ]
        )

        # -------------------------
        # Layout
        # -------------------------
        container = ft.Column(
            [
                ft.Container(toolbar, padding=8),
                ft.Stack(
                    [
                        editor_container,
                        code_overlay,
                        hint_container,
                    ],
                    expand=True,
                ),
            ],
            expand=True,
        )

        # -------------------------
        # Start watchers
        # -------------------------
        page.run_task(_watch_selection)
        page.run_task(_watch_cursor)

        return container


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

    # Bottom console (1/3 screen height), shown on Run click; use code display for highlighting
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
        from gui.components.settings import get_debug_log_path

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
                    from gui.chat_with_the_assistants.workflow_run_utils import collect_workflow_errors
                    errs = collect_workflow_errors(outputs)
                    if errs:
                        _append_console("")
                        _append_console("--- Errors ---")
                        for uid, err in errs:
                            _append_console(f"  {uid}: {err[:200]}")
                except Exception:
                    pass
                # Grep the debug log (same path as injected for Debug units above)
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
        # Aggregate passes run_workflow port 0 (data) into merge_response.run_output, so run_output
        # is often the raw executor outputs dict (unit_id -> port_values). Otherwise it may be
        # the unit output shape {"data": ..., "error": ...}.
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
                    from gui.components.settings import get_debug_log_path
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
