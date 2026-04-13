"""
Dialog to view/edit the process graph as JSON in a code editor, with code block overlay.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

import flet as ft

from core.schemas.process_graph import CodeBlock, Comment, Connection, ProcessGraph, Unit

from gui.components.workflow_tab.dialogs.dialog_common import dict_to_graph
from gui.components.workflow_tab.editor.graph_code_editor.overlay_editor import (
    create_graph_json_overlay,
    get_block_index_from_cursor,
)
from gui.utils.code_editor import build_code_editor
from gui.utils.keyboard_commands import create_keyboard_handler
from gui.utils.notifications import show_toast


def open_view_graph_code_dialog(
    page: ft.Page,
    graph: ProcessGraph | None,
    *,
    unit_id: str | None = None,
    comment_id: str | None = None,
    on_graph_saved: Callable[[ProcessGraph], None] | None = None,
    chat_panel_api: dict[str, Any] | None = None,
) -> None:
    """Graph / code block editor dialog with position-mapped overlay editing."""

    editor_width = 800  # default width

    # --- Build central payload ---
    try:
        if graph is None:
            raw_payload = {}
        elif comment_id:
            comment = next((c for c in (graph.comments or []) if c.id == comment_id), None)
            if comment is None:
                raw_payload = {"error": f"Comment {comment_id} not found"}
            else:
                # Preserve the comment structure exactly; we'll treat its "info" field
                # as the editable text block (no new keys, no structural changes).
                raw_payload = comment.model_dump()
        elif unit_id:
            unit = graph.get_unit(unit_id)
            if unit is None:
                raw_payload = {"error": f"Unit {unit_id} not found"}
            else:
                connections = [c.model_dump(by_alias=True) for c in graph.connections if c.from_id == unit_id or c.to_id == unit_id]
                code_blocks_for_unit = [b.model_dump(by_alias=True) for b in graph.code_blocks if b.id == unit_id]
                raw_payload = {"unit": unit.model_dump(by_alias=True), "connections": connections}
                if code_blocks_for_unit:
                    raw_payload["code_blocks"] = code_blocks_for_unit
        else:
            raw_payload = graph.model_dump(by_alias=True)
    except Exception as ex:
        raw_payload = {"error": str(ex)}

    # --- Refs for mutable state ---
    full_json_ref = [raw_payload]
    block_ranges_ref = [[]]

    # --- JSON formatter with block ranges (map comment.info as editable block) ---
    def format_json_with_block_map(data: dict):
        parts: list[str] = []
        ranges: list[tuple[int, int, tuple]] = []
        cursor = 0

        def add(txt: str):
            nonlocal cursor
            parts.append(txt)
            cursor += len(txt)

        def indent_block(text: str, spaces: int) -> str:
            """Indent multiline JSON safely without introducing blank lines."""
            prefix = " " * spaces
            return "\n".join(prefix + line for line in text.splitlines() if line.strip())

        def dump_clean(obj) -> str:
            """Stable JSON dump without trailing newline issues."""
            return json.dumps(obj, indent=2, ensure_ascii=False)

        add("{\n")
        items = list(data.items())

        is_comment_root = isinstance(data, dict) and data.get("id", "").startswith("comment_")

        for idx, (key, value) in enumerate(items):
            is_last = idx == len(items) - 1

            # --- ROOT comment "info" ---
            if is_comment_root and key == "info" and isinstance(value, str):
                raw = dump_clean({key: value})
                inner = raw.strip()[1:-1]  # remove outer braces

                rendered = indent_block(inner, 2)

                start = cursor
                add(rendered)
                end = cursor

                info_repr = json.dumps(value, ensure_ascii=False)
                val_idx = rendered.find(info_repr)

                if val_idx != -1:
                    ranges.append((
                        start + val_idx,
                        start + val_idx + len(info_repr),
                        ("comment_info", data.get("id"))
                    ))
                else:
                    ranges.append((start, end, ("comment_obj", data.get("id"))))

            # --- code_blocks ---
            elif key == "code_blocks" and isinstance(value, list):
                add(f'  "{key}": [\n')

                for i, block in enumerate(value):
                    raw = dump_clean(block)
                    rendered = indent_block(raw, 4)

                    start = cursor
                    add(rendered)
                    end = cursor

                    ranges.append((start, end, ("code_blocks", i)))

                    if i < len(value) - 1:
                        add(",\n")
                    else:
                        add("\n")

                add("  ]")

            # --- nested comment object ---
            elif (
                isinstance(value, dict)
                and "info" in value
                and isinstance(value.get("id", ""), str)
                and value.get("id", "").startswith("comment_")
            ):
                raw = dump_clean(value)
                rendered = indent_block(raw, 2)

                start = cursor
                add(rendered)
                end = cursor

                try:
                    parsed = json.loads(raw)
                    info_value = parsed.get("info", "")
                    info_repr = json.dumps(info_value, ensure_ascii=False)

                    key_idx = raw.find('"info":')
                    val_idx = raw.find(info_repr, key_idx)

                    if val_idx != -1:
                        chars_before = val_idx
                        lines_before = raw[:val_idx].count("\n")

                        rendered_offset = chars_before + 2 * (lines_before + 1)

                        info_start = start + rendered_offset
                        info_end = info_start + len(info_repr)

                        ranges.append((info_start, info_end, ("comment_info", value.get("id"))))
                    else:
                        ranges.append((start, end, ("comment_obj", value.get("id"))))

                except Exception:
                    ranges.append((start, end, ("comment_obj", value.get("id"))))

            # --- DEFAULT ---
            else:
                raw = dump_clean({key: value})
                inner = raw.strip()[1:-1]

                rendered = indent_block(inner, 2)
                add(rendered)

            # --- separator (controlled, single source of truth) ---
            if not is_last:
                add(",\n")
            else:
                add("\n")

        add("}")
        return "".join(parts), ranges

    # --- Build editor from state ---
    def build_editor_from_state():
        formatted, ranges = format_json_with_block_map(full_json_ref[0])
        block_ranges_ref[0] = ranges
        return build_code_editor(
            code=formatted,
            expand=True,
            page=page,
            language="json",
        )

    code_editor_control, get_value, show_find_bar, hide_find_bar, get_selection_range, _ = (
        build_editor_from_state()
    )
    editor_container = ft.Container(code_editor_control, expand=True)

    def refresh_editor():
        nonlocal code_editor_control, get_value, show_find_bar, hide_find_bar, get_selection_range
        code_editor_control, get_value, show_find_bar, hide_find_bar, get_selection_range, _ = (
            build_editor_from_state()
        )
        editor_container.content = code_editor_control
        editor_container.update()

    _overlay = create_graph_json_overlay(
        page,
        full_json_ref=full_json_ref,
        refresh_editor=refresh_editor,
        editor_container=editor_container,
        graph=graph,
        hide_editor_when_overlay=True,
    )
    code_overlay = _overlay.code_overlay
    active_editor = _overlay.active_editor
    close_overlay = _overlay.close_overlay
    show_json_editor = _overlay.show_json_editor
    open_code_editor = _overlay.open_code_editor

    def trigger_edit_code_block():
        idx = get_block_index_from_cursor(
            get_selection_range, block_ranges_ref[0], active_editor
        )
        if idx is not None:
            open_code_editor(idx)

    page.on_keyboard_event = create_keyboard_handler(
        chain_to=page.on_keyboard_event,
        on_find=show_find_bar,
        on_escape=hide_find_bar,
        on_edit_code_block=trigger_edit_code_block
    )

    # --- Hint UI (positioned inside Stack) ---
    hint_container = ft.Container(
        content=ft.Text("Use Cmd+E to edit the code block or comment", size=12, color=ft.Colors.GREY_400),
        visible=False,
        right=20,
        bottom=20,
    )

    # --- Chat icon ---
    CHAT_ICON_INACTIVE_COLOR = ft.Colors.PRIMARY
    CHAT_ICON_ACTIVE_COLOR = ft.Colors.GREEN_500
    dlg_holder: list[ft.AlertDialog | None] = [None]
    watch_token_ref: list[int] = [0]
    this_watch = watch_token_ref[0] + 1
    watch_token_ref[0] = this_watch
    chat_icon_btn_ref: list[ft.IconButton | None] = [None]

    async def _add_selection_to_chat(_e: ft.ControlEvent):
        api = chat_panel_api if chat_panel_api else {}
        fn = api.get("add_code_reference")
        if not callable(fn):
            await show_toast(page, "Assistants chat is not ready yet.")
            return
        rng = get_selection_range()
        if not rng:
            await show_toast(page, "Select part of the JSON first.")
            return
        a, b = rng
        if a > b:
            a, b = b, a
        full = get_value() or ""
        a = max(0, min(len(full), a))
        b = max(0, min(len(full), b))
        snippet = full[a:b]
        if not snippet.strip():
            await show_toast(page, "Selection is empty.")
            return
        try:
            fn(snippet=snippet, start=a, end=b)
        except Exception as ex:
            await show_toast(page, str(ex)[:120])

    async def _watch_dialog_selection_for_chat_icon():
        """Match workflow tab: chat icon turns green for any non-empty selection; Cmd+E hint only inside code/comment blocks."""
        last_has_chat = None
        last_hint = None
        while watch_token_ref[0] == this_watch:
            dlg = dlg_holder[0]
            if dlg is None or not dlg.open:
                break
            rng = None
            try:
                rng = get_selection_range()
            except Exception:
                rng = None
            has_chat_selection = False
            selection_in_editable_block = False
            if rng is not None:
                a, b = rng
                if a > b:
                    a, b = b, a
                try:
                    full = get_value() or ""
                except Exception:
                    full = ""
                if a < b and full[a:b].strip():
                    has_chat_selection = True
                    for start, end, _ in block_ranges_ref[0]:
                        if not (b < start or a > end):
                            selection_in_editable_block = True
                            break
            if last_has_chat is None or has_chat_selection != last_has_chat:
                btn = chat_icon_btn_ref[0]
                if btn:
                    btn.icon_color = (
                        CHAT_ICON_ACTIVE_COLOR if has_chat_selection else CHAT_ICON_INACTIVE_COLOR
                    )
                    try:
                        btn.update()
                    except Exception:
                        pass
                    try:
                        page.update()
                    except Exception:
                        pass
                last_has_chat = has_chat_selection
            # Cmd+E hint: only when cursor/selection is in an overlay-mapped block (json editor visible)
            try:
                if active_editor[0] == "json":
                    if last_hint is None or selection_in_editable_block != last_hint:
                        hint_container.visible = selection_in_editable_block
                        hint_container.update()
                        last_hint = selection_in_editable_block
                else:
                    if hint_container.visible:
                        hint_container.visible = False
                        hint_container.update()
                    last_hint = False
            except Exception:
                pass
            await asyncio.sleep(0.25)

    chat_icon_btn = ft.IconButton(
        icon=ft.Icons.CHAT_BUBBLE_OUTLINE,
        tooltip="Add selection to assistants chat",
        on_click=lambda e: page.run_task(_add_selection_to_chat, e),
        icon_color=CHAT_ICON_INACTIVE_COLOR,
    )
    chat_icon_btn_ref[0] = chat_icon_btn

    # --- Dialog content (use Stack so hint can be absolutely positioned) ---
    content_stack = ft.Stack(expand=True, controls=[
        ft.Column([editor_container, code_overlay], expand=True),
        hint_container,  # positioned with right/bottom inside the Stack
    ])

    title = ft.Text(
        "Comment (code)" if comment_id else ("Unit (code)" if unit_id else "Graph (code)")
    )

    def _close_dlg():
        watch_token_ref[0] += 1
        dlg_holder[0] = None
        dlg.open = False
        page.update()

    # Apply/Delete/Copy buttons
    left_buttons: list[ft.Control] = []
    def apply_click(_e):
        if on_graph_saved is None or graph is None:
            return
        try:
            text = get_value()
            data = json.loads(text)
            if unit_id:
                unit_data = data.get("unit")
                conns_data = data.get("connections", [])
                blocks_payload = data.get("code_blocks", [])
                if not unit_data:
                    return
                updated_unit = Unit.model_validate(unit_data)
                new_units = [u for u in graph.units if u.id != unit_id] + [updated_unit]
                new_connections = [
                    c for c in graph.connections if c.from_id != unit_id and c.to_id != unit_id
                ] + [Connection.model_validate(c) for c in conns_data]
                other_blocks = [b for b in graph.code_blocks if b.id != unit_id]
                updated_blocks = [CodeBlock.model_validate(b) for b in blocks_payload] if isinstance(blocks_payload, list) else []
                new_graph = graph.model_copy(
                    update={
                        "units": new_units,
                        "connections": new_connections,
                        "code_blocks": other_blocks + updated_blocks,
                    }
                )
            elif comment_id:
                # For comments, data is the comment object; ensure info is taken from that object (it may have been edited)
                updated_comment = Comment.model_validate(data)
                new_comments = [c for c in (graph.comments or []) if c.id != comment_id] + [updated_comment]
                new_graph = graph.model_copy(update={"comments": new_comments})
            else:
                new_graph = dict_to_graph(data)
            on_graph_saved(new_graph)
            _close_dlg()
        except Exception as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(str(ex)), open=True)
            page.update()

    def delete_click(_e):
        if graph is None or on_graph_saved is None:
            return
        if unit_id:
            new_units = [u for u in graph.units if u.id != unit_id]
            new_connections = [c for c in graph.connections if c.from_id != unit_id and c.to_id != unit_id]
            new_code_blocks = [b for b in graph.code_blocks if b.id != unit_id]
            new_layout = {k: v for k, v in (graph.layout or {}).items() if k != unit_id} or None
            new_graph = graph.model_copy(
                update={
                    "units": new_units,
                    "connections": new_connections,
                    "code_blocks": new_code_blocks,
                    "layout": new_layout,
                }
            )
        elif comment_id:
            new_comments = [c for c in (graph.comments or []) if c.id != comment_id]
            new_graph = graph.model_copy(update={"comments": new_comments or None})
        else:
            return
        on_graph_saved(new_graph)
        _close_dlg()

    left_buttons.append(ft.TextButton("Apply", on_click=apply_click))
    if unit_id or comment_id:
        left_buttons.append(ft.TextButton("Delete", on_click=delete_click))

    async def copy_click(_e):
        await page.clipboard.set(get_value())
        await show_toast(page, "Copied!")

    dlg = ft.AlertDialog(
        modal=True,
        title=title,
        content=ft.Container(
            content=ft.Column([
                ft.Row([
                    *left_buttons,
                    ft.Container(expand=True),
                    ft.IconButton(icon=ft.Icons.COPY, tooltip="Copy", on_click=copy_click, icon_color=ft.Colors.PRIMARY),
                    chat_icon_btn
                ], spacing=8),
                content_stack
            ], expand=True),
            width=editor_width,
            bgcolor="#12161A",
        ),
        actions=[ft.TextButton("Close", on_click=lambda e: _close_dlg())],
    )

    dlg_holder[0] = dlg
    page.overlay.append(dlg)
    dlg.open = True
    page.update()

    # ensure json editor visible on open
    show_json_editor()

    try:
        page.run_task(_watch_dialog_selection_for_chat_icon)
    except Exception:
        pass

    
