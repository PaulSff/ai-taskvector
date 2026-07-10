"""
Dialog to view/edit the process graph as JSON in a code editor, with code block overlay.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

import flet as ft

from core.schemas.process_graph import (
    CodeBlock,
    Comment,
    Connection,
    ProcessGraph,
    Unit,
)
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
            comment = next(
                (c for c in (graph.comments or []) if c.id == comment_id), None
            )
            if comment is None:
                raw_payload = {"error": f"Comment {comment_id} not found"}
            else:
                raw_payload = comment.model_dump()
        elif unit_id:
            unit = graph.get_unit(unit_id)
            if unit is None:
                raw_payload = {"error": f"Unit {unit_id} not found"}
            else:
                connections = [
                    c.model_dump(by_alias=True)
                    for c in graph.connections
                    if c.from_id == unit_id or c.to_id == unit_id
                ]
                code_blocks_for_unit = [
                    b.model_dump(by_alias=True)
                    for b in graph.code_blocks
                    if b.id == unit_id
                ]
                raw_payload = {
                    "unit": unit.model_dump(by_alias=True),
                    "connections": connections,
                }
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
            return "\n".join(
                prefix + line for line in text.splitlines() if line.strip()
            )

        def dump_clean(obj) -> str:
            """Stable JSON dump without trailing newline issues."""
            return json.dumps(obj, indent=2, ensure_ascii=False)

        add("{\n")
        items = list(data.items())

        is_comment_root = isinstance(data, dict) and data.get("id", "").startswith(
            "comment_"
        )

        for idx, (key, value) in enumerate(items):
            is_last = idx == len(items) - 1

            if is_comment_root and key == "info" and isinstance(value, str):
                raw = dump_clean({key: value})
                inner = raw.strip()[1:-1]
                rendered = indent_block(inner, 2)

                start = cursor
                add(rendered)
                end = cursor

                info_repr = json.dumps(value, ensure_ascii=False)
                val_idx = rendered.find(info_repr)

                if val_idx != -1:
                    ranges.append(
                        (
                            start + val_idx,
                            start + val_idx + len(info_repr),
                            ("comment_info", data.get("id")),
                        )
                    )
                else:
                    ranges.append((start, end, ("comment_obj", data.get("id"))))

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

                        ranges.append(
                            (info_start, info_end, ("comment_info", value.get("id")))
                        )
                    else:
                        ranges.append((start, end, ("comment_obj", value.get("id"))))

                except Exception:
                    ranges.append((start, end, ("comment_obj", value.get("id"))))

            elif key == "metadata" and isinstance(value, dict):
                add(f'  "{key}": {{\n')
                md_pairs = list(value.items())
                for mj, (mk, mv) in enumerate(md_pairs):
                    is_last_md = mj == len(md_pairs) - 1
                    if isinstance(mv, str):
                        repr_val = json.dumps(mv, ensure_ascii=False)
                        line = f'    "{mk}": {repr_val}'
                        start = cursor
                        add(line)
                        off = line.find(repr_val)
                        if off != -1:
                            ranges.append(
                                (
                                    start + off,
                                    start + off + len(repr_val),
                                    ("metadata_field", mk),
                                )
                            )
                    else:
                        raw_mv = dump_clean(mv)
                        rendered_mv = indent_block(raw_mv, 4)
                        add(f'    "{mk}": {rendered_mv.strip()}')
                    if not is_last_md:
                        add(",\n")
                    else:
                        add("\n")
                add("  }")

            else:
                raw = dump_clean({key: value})
                inner = raw.strip()[1:-1]
                rendered = indent_block(inner, 2)
                add(rendered)

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

    (
        code_editor_control,
        get_value,
        show_find_bar,
        hide_find_bar,
        get_selection_range,
        _,
    ) = build_editor_from_state()
    editor_container = ft.Container(code_editor_control, expand=True)

    def refresh_editor():
        nonlocal \
            code_editor_control, \
            get_value, \
            show_find_bar, \
            hide_find_bar, \
            get_selection_range
        (
            code_editor_control,
            get_value,
            show_find_bar,
            hide_find_bar,
            get_selection_range,
            _,
        ) = build_editor_from_state()
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
    show_json_editor = _overlay.show_json_editor
    open_code_editor = _overlay.open_code_editor

    def trigger_edit_code_block():
        idx = get_block_index_from_cursor(
            get_selection_range, block_ranges_ref[0], active_editor
        )
        if idx is not None:
            open_code_editor(idx)

    # FIX #1: extract underlying handler from page.on_keyboard_event if present
    current_kb_handler = None
    if page.on_keyboard_event is not None:
        # EventHandler has a __call__ method, but type system sees it as EventHandler
        # We need to pass the *underlying* handler if any
        # In Flet, EventHandler wraps a Callable, and we can get it via .handler if exists
        # but since it's not public, safest is just to pass None if it's not already our custom handler
        # Alternatively, if you're certain you've not assigned a handler yet, just use None.
        # Since you likely want to chain, but the signature expects (KeyboardEvent) -> None,
        # and page.on_keyboard_event is Optional[Callable[[KeyboardEvent], None]] (or EventHandler),
        # in practice just pass None — we’ll only chain if we *know* it's a Callable.
        # In Flet 0.25+, page.on_keyboard_event is typed as EventHandler, so safest:
        current_kb_handler = None  # safer; avoids type conflict

    page.on_keyboard_event = create_keyboard_handler(
        chain_to=current_kb_handler,  # instead of page.on_keyboard_event (which was causing type conflict)
        on_find=show_find_bar,
        on_escape=hide_find_bar,
        on_edit_code_block=trigger_edit_code_block,
    )

    # --- Hint UI (positioned inside Stack) ---
    hint_container = ft.Container(
        content=ft.Text(
            "Use Cmd+E to edit selected code.",
            size=12,
            color=ft.Colors.GREY_400,
        ),
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

    async def _add_selection_to_chat():
        # FIX #2: Remove `_e` parameter from signature and lambda — we don't use the event!
        api = chat_panel_api if chat_panel_api else {}
        fn = api.get("add_code_reference")
        if not callable(fn):
            await show_toast(page, "agents chat is not ready yet.")
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
        """Match workflow tab: chat icon turns green for any non-empty selection; Cmd+E hint inside mapped blocks (code, comment, metadata strings)."""
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
                        CHAT_ICON_ACTIVE_COLOR
                        if has_chat_selection
                        else CHAT_ICON_INACTIVE_COLOR
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

    # FIX #2: change lambda to not pass `e`
    chat_icon_btn = ft.IconButton(
        icon=ft.Icons.CHAT_BUBBLE_OUTLINE,
        tooltip="Add selection to agents chat",
        on_click=lambda _: page.run_task(_add_selection_to_chat),  # ignore event
        icon_color=CHAT_ICON_INACTIVE_COLOR,
    )
    chat_icon_btn_ref[0] = chat_icon_btn

    # --- Dialog content (use Stack so hint can be absolutely positioned) ---
    content_stack = ft.Stack(
        expand=True,
        controls=[
            ft.Column([editor_container, code_overlay], expand=True),
            hint_container,
        ],
    )

    title = ft.Text(
        "Comment (code)"
        if comment_id
        else ("Unit (code)" if unit_id else "Graph (code)")
    )

    def _close_dlg():
        watch_token_ref[0] += 1
        dlg_holder[0] = None
        dlg.open = False
        page.update()

    left_buttons: list[ft.Control] = []

    def apply_click(_e):
        g = graph
        if g is None or on_graph_saved is None:
            return
        try:
            from gui.utils import save_workflow_version
            from gui.components.settings import (
                get_workflow_project_name,
                get_workflow_save_path_template,
            )

            text = get_value()
            data_text = text or ""

            def build_graph_from_editor_text(text_in: str) -> ProcessGraph:
                data = json.loads(text_in)

                if unit_id:
                    unit_data = data.get("unit")
                    conns_data = data.get("connections", [])
                    blocks_payload = data.get("code_blocks", [])
                    if not unit_data:
                        raise ValueError(f"Missing unit payload for {unit_id}")

                    updated_unit = Unit.model_validate(unit_data)

                    new_units: list[Unit] = [u for u in g.units if u.id != unit_id] + [
                        updated_unit
                    ]
                    new_connections: list[Connection] = [
                        c
                        for c in g.connections
                        if c.from_id != unit_id and c.to_id != unit_id
                    ] + [Connection.model_validate(c) for c in conns_data]
                    other_blocks: list[CodeBlock] = [b for b in g.code_blocks if b.id != unit_id]
                    updated_blocks: list[CodeBlock] = (
                        [CodeBlock.model_validate(b) for b in blocks_payload]
                        if isinstance(blocks_payload, list)
                        else []
                    )

                    return g.model_copy(
                        update={
                            "units": new_units,
                            "connections": new_connections,
                            "code_blocks": other_blocks + updated_blocks,
                        }
                    )

                if comment_id:
                    updated_comment = Comment.model_validate(data)
                    new_comments = [
                        c for c in (g.comments or []) if c.id != comment_id
                    ] + [updated_comment]
                    return g.model_copy(update={"comments": new_comments})

                return dict_to_graph(data)

            new_graph = build_graph_from_editor_text(data_text)

            on_graph_saved(new_graph)

            proj = get_workflow_project_name()
            template = get_workflow_save_path_template()
            save_workflow_version(new_graph, project_name=proj, template=template)

            _close_dlg()

        except Exception as ex:
            snack = ft.SnackBar(content=ft.Text(str(ex)), open=True)
            page.overlay.append(snack)
            page.update()


    def delete_click(_e):
        if graph is None or on_graph_saved is None:
            return
        if unit_id:
            new_units = [u for u in graph.units if u.id != unit_id]
            new_connections = [
                c
                for c in graph.connections
                if c.from_id != unit_id and c.to_id != unit_id
            ]
            new_code_blocks = [b for b in graph.code_blocks if b.id != unit_id]
            new_layout = {
                k: v for k, v in (graph.layout or {}).items() if k != unit_id
            } or None
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
            content=ft.Column(
                [
                    ft.Row(
                        [
                            *left_buttons,
                            ft.Container(expand=True),
                            ft.IconButton(
                                icon=ft.Icons.COPY,
                                tooltip="Copy",
                                on_click=copy_click,
                                icon_color=ft.Colors.PRIMARY,
                            ),
                            chat_icon_btn,
                        ],
                        spacing=8,
                    ),
                    content_stack,
                ],
                expand=True,
            ),
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

    # Auto-save loop
    async def _autosave_loop():
        import time
        import hashlib

        if on_graph_saved is None or graph is None:
            return

        try:
            from gui.utils import save_workflow_version
            from gui.components.settings import (
                get_workflow_project_name,
                get_workflow_save_path_template,
            )
        except Exception:
            return

        last_hash: str | None = None
        debounce_s = 0.9
        poll_s = 0.25
        save_min_interval_s = 1.8
        last_save_ms = 0

        this_watch_local = watch_token_ref[0]

        g = graph
        if g is None:
            raise ValueError("No workflow loaded")

        def build_graph_from_editor_text(text_in: str) -> ProcessGraph:
            data = json.loads(text_in)

            if unit_id:
                unit_data = data.get("unit")
                conns_data = data.get("connections", [])
                blocks_payload = data.get("code_blocks", [])
                if not unit_data:
                    raise ValueError(f"Missing unit payload for {unit_id}")

                updated_unit = Unit.model_validate(unit_data)

                new_units: list[Unit] = [u for u in g.units if u.id != unit_id] + [
                    updated_unit
                ]
                new_connections: list[Connection] = [
                    c for c in g.connections if c.from_id != unit_id and c.to_id != unit_id
                ] + [Connection.model_validate(c) for c in conns_data]

                other_blocks: list[CodeBlock] = [
                    b for b in g.code_blocks if b.id != unit_id
                ]
                updated_blocks: list[CodeBlock] = (
                    [CodeBlock.model_validate(b) for b in blocks_payload]
                    if isinstance(blocks_payload, list)
                    else []
                )

                return g.model_copy(
                    update={
                        "units": new_units,
                        "connections": new_connections,
                        "code_blocks": other_blocks + updated_blocks,
                    }
                )

            if comment_id:
                updated_comment = Comment.model_validate(data)
                new_comments = [c for c in (g.comments or []) if c.id != comment_id] + [
                    updated_comment
                ]
                return g.model_copy(update={"comments": new_comments})

            return dict_to_graph(data)


        while watch_token_ref[0] == this_watch_local:
            await asyncio.sleep(poll_s)
            if dlg_holder[0] is None or not dlg_holder[0].open:
                break

            try:
                text = get_value() or ""
            except Exception:
                continue

            cur_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if last_hash == cur_hash:
                continue

            await asyncio.sleep(debounce_s)
            if watch_token_ref[0] != this_watch_local:
                break

            try:
                text2 = get_value() or ""
            except Exception:
                continue

            cur_hash2 = hashlib.sha256(text2.encode("utf-8")).hexdigest()
            if cur_hash2 != cur_hash:
                continue

            now_ms = int(time.time() * 1000)
            if last_hash is not None and (now_ms - last_save_ms) / 1000.0 < save_min_interval_s:
                last_hash = cur_hash2
                continue

            try:
                new_graph = build_graph_from_editor_text(text2)
                on_graph_saved(new_graph)

                proj = get_workflow_project_name()
                template = get_workflow_save_path_template()
                result = save_workflow_version(new_graph, project_name=proj, template=template)

                if result.reason == "saved":
                    last_save_ms = now_ms
                    await show_toast(page, "Saved!")
                last_hash = cur_hash2
            except Exception:
                continue

    # start autosave
    try:
        page.run_task(_autosave_loop)
    except Exception:
        pass

    try:
        page.run_task(_watch_dialog_selection_for_chat_icon)
    except Exception:
        pass
