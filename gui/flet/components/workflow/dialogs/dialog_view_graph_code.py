"""
Dialog to view/edit the process graph as JSON in a code editor, with code block overlay.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

import flet as ft

from core.schemas.process_graph import CodeBlock, Comment, Connection, ProcessGraph, Unit

from gui.flet.components.workflow.dialogs.dialog_common import dict_to_graph
from gui.flet.tools.code_editor import build_code_editor
from gui.flet.tools.keyboard_commands import create_keyboard_handler
from gui.flet.tools.notifications import show_toast


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

    code_editor_control, get_value, show_find_bar, hide_find_bar, get_selection_range = build_editor_from_state()
    editor_container = ft.Container(code_editor_control, expand=True)

    def refresh_editor():
        nonlocal code_editor_control, get_value, show_find_bar, hide_find_bar, get_selection_range
        code_editor_control, get_value, show_find_bar, hide_find_bar, get_selection_range = build_editor_from_state()
        editor_container.content = code_editor_control
        editor_container.update()

    # --- Overlay editor for a single block ---
    code_overlay = ft.Container(visible=False, expand=True, bgcolor=ft.Colors.with_opacity(0.92, ft.Colors.BLACK))

    def close_overlay():
        code_overlay.content = None
        show_json_editor()

    def open_code_editor(block_index):
        # block_index is either ("code_blocks", i) or ("comment_info", comment_id) or ("comment_obj", comment_id)
        if isinstance(block_index, tuple) and block_index[0] == "code_blocks":
            blocks = full_json_ref[0].get("code_blocks", [])
            _, i = block_index
            if not isinstance(blocks, list) or i >= len(blocks):
                return
            block = blocks[i]
            lang = block.get("language", "python")
            source = block.get("source", "")
            is_comment_info = False
            comment_id_local = None
        elif isinstance(block_index, tuple) and block_index[0] in ("comment_info", "comment_obj"):
            _, comment_id_local = block_index
            # find the comment object in the payload
            payload = full_json_ref[0]
            # payload is the comment dict itself when comment_id was provided
            comment_obj = payload if payload.get("id") == comment_id_local else None
            if comment_obj is None:
                # try to find in graph.comments
                comment_obj = next((c for c in (graph.comments or []) if c.id == comment_id_local), None)
                if comment_obj:
                    comment_obj = comment_obj.model_dump()
            if not comment_obj:
                return
            lang = "text"
            source = comment_obj.get("info", "") or ""
            is_comment_info = True
        else:
            return

        # For text, use a simple TextField (acts like MD editor)
        if lang == "text":
            text_field = ft.TextField(value=source, multiline=True, expand=True)

            def block_get_value():
                return text_field.value

            def apply_changes(e=None):
                # write back into payload: update the comment object's info field only
                if isinstance(block_index, tuple) and block_index[0] in ("comment_info", "comment_obj"):
                    # payload is the whole comment object when dialog opened for comment
                    full_json_ref[0]["info"] = block_get_value()
                else:
                    # code_blocks path
                    full_json_ref[0]["code_blocks"][i]["source"] = block_get_value()
                refresh_editor()
                close_overlay()

            code_overlay.content = ft.Column([
                ft.Row([
                    ft.Text(f"Editing: {comment_id_local or block.get('id', i)}"),
                    ft.IconButton(icon=ft.Icons.CHECK, on_click=apply_changes),
                    ft.IconButton(icon=ft.Icons.CLOSE, on_click=lambda e: close_overlay())
                ]),
                text_field
            ], expand=True)
            show_block_overlay()
            return

        # fallback for non-text: use build_code_editor
        block_editor, block_get_value, *_ = build_code_editor(
            code=source,
            expand=True,
            page=page,
            language=lang,
        )

        def apply_changes(e=None):
            if isinstance(block_index, tuple) and block_index[0] in ("comment_info", "comment_obj"):
                full_json_ref[0]["info"] = block_get_value()
            else:
                full_json_ref[0]["code_blocks"][i]["source"] = block_get_value()
            refresh_editor()
            close_overlay()

        code_overlay.content = ft.Column([
            ft.Row([
                ft.Text(f"Editing: {comment_id_local or block.get('id', i)}"),
                ft.IconButton(icon=ft.Icons.CHECK, on_click=apply_changes),
                ft.IconButton(icon=ft.Icons.CLOSE, on_click=lambda e: close_overlay())
            ]),
            block_editor
        ], expand=True)
        show_block_overlay()

    # --- Active editor state helpers ---
    active_editor = ["json"]

    def show_json_editor():
        active_editor[0] = "json"
        editor_container.visible = True
        code_overlay.visible = False
        try:
            editor_container.update()
            code_overlay.update()
        except Exception:
            pass

    def show_block_overlay():
        active_editor[0] = "block"
        editor_container.visible = False
        code_overlay.visible = True
        try:
            editor_container.update()
            code_overlay.update()
        except Exception:
            pass

    def hide_all_overlays():
        active_editor[0] = None
        editor_container.visible = False
        code_overlay.visible = False
        try:
            editor_container.update()
            code_overlay.update()
        except Exception:
            pass

    # --- Detect block under cursor ---
    def get_block_index_from_cursor():
        if active_editor[0] != "json":
            return None
        try:
            rng = get_selection_range()
            if not rng:
                return None
            caret = min(rng)
            for start, end, idx in block_ranges_ref[0]:
                if start <= caret <= end:
                    return idx
            return None
        except Exception:
            return None

    # --- Shortcut Cmd/Ctrl+E ---
    def trigger_edit_code_block():
        if active_editor[0] != "json":
            return
        idx = get_block_index_from_cursor()
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
        content=ft.Text("Use Cmd+E to edit the code_block", size=12, color=ft.Colors.GREY_400),
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
        full = get_value()
        rng = get_selection_range()
        if not rng:
            await show_toast(page, "Select part of the JSON first.")
            return
        a, b = rng
        snippet = full[a:b]
        if not snippet.strip():
            await show_toast(page, "Selection is empty.")
            return
        try:
            fn(snippet=snippet, start=a, end=b)
        except Exception as ex:
            await show_toast(page, str(ex)[:120])

    async def _watch_dialog_selection_for_chat_icon():
        last_has_selection = None
        while watch_token_ref[0] == this_watch:
            dlg = dlg_holder[0]
            if dlg is None or not dlg.open:
                break
            rng = None
            try:
                rng = get_selection_range()
            except Exception:
                rng = None
            has_selection = False
            if rng is not None:
                a, b = rng
                if a < b:
                    full = get_value()
                    if full[a:b].strip():
                        # NEW: ensure selection overlaps a valid editable block
                        for start, end, _ in block_ranges_ref[0]:
                            # overlap check
                            if not (b < start or a > end):
                                has_selection = True
                                break
            if last_has_selection is None or has_selection != last_has_selection:
                btn = chat_icon_btn_ref[0]
                if btn:
                    btn.icon_color = CHAT_ICON_ACTIVE_COLOR if has_selection else CHAT_ICON_INACTIVE_COLOR
                    try:
                        btn.update()
                    except Exception:
                        pass
                # Only show hint when json editor is visible
                try:
                    if active_editor[0] == "json":
                        hint_container.visible = has_selection
                        hint_container.update()
                    else:
                        if hint_container.visible:
                            hint_container.visible = False
                            hint_container.update()
                except Exception:
                    pass
                last_has_selection = has_selection
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
                new_graph = ProcessGraph(
                    environment_type=graph.environment_type,
                    units=new_units,
                    connections=new_connections,
                    code_blocks=other_blocks + updated_blocks,
                    layout=graph.layout,
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
            new_graph = ProcessGraph(
                environment_type=graph.environment_type,
                units=new_units,
                connections=new_connections,
                code_blocks=new_code_blocks,
                layout=new_layout,
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

    
