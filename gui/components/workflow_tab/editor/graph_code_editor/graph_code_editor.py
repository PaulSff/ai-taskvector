"""
Full-graph JSON code view: custom formatter with block ranges, overlay editor, toolbar, chat selection.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Callable

import flet as ft

from core.schemas.process_graph import ProcessGraph

from gui.components.workflow_tab.dialogs import dict_to_graph

from .overlay_editor import (
    create_graph_json_overlay,
    get_block_index_from_cursor,
)
from gui.utils.code_editor import build_code_editor
from gui.utils.keyboard_commands import create_keyboard_handler

# When applying raw JSON from the code editor, merge these top-level keys from the previous graph
# if they are absent from the parsed JSON (partial paste / round-trip gaps) so comments, todo_list,
# origin, etc. are not dropped accidentally. Structural keys (units, connections, …) must appear in the editor.
MERGE_GRAPH_KEYS_IF_MISSING: frozenset[str] = frozenset(
    {
        "comments",
        "todo_list",
        "metadata",
        "origin",
        "origin_format",
        "runtime",
        "tabs",
        "environments",
        "layout",
    }
)


def build_graph_code_view(
    page: ft.Page,
    graph_ref: list[ProcessGraph | None],
    *,
    selection_watch_token_ref: list[int],
    on_graph_saved: Callable[[ProcessGraph | None], None],
    show_graph_view: Callable[[], None],
    show_toast: Callable[[ft.Page, str], None],
    chat_panel_api: dict[str, Any] | None = None,
) -> ft.Control:
    """Build the workflow tab code view: position-mapped JSON editor, Cmd+E blocks, find, apply, chat share."""

    try:
        raw_payload = graph_ref[0].model_dump(by_alias=True) if graph_ref[0] else {}
    except Exception:
        raw_payload = {}

    full_json_ref = [raw_payload]
    block_ranges_ref: list[list[tuple[int, int, Any]]] = [[]]

    # -------------------------
    # JSON formatter + position map
    # -------------------------
    def format_json_with_block_map(data: dict) -> tuple[str, list[tuple[int, int, Any]]]:
        parts: list[str] = []
        block_ranges: list[tuple[int, int, Any]] = []
        cursor = 0

        def add(txt: str) -> None:
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
                            val_idx = block_str.find(info_repr, key_idx) if key_idx != -1 else -1
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
        chain_to=page.on_keyboard_event,  # keep previous chain
        on_find=show_find_bar,  # existing find bar shortcut
        on_escape=hide_find_bar,  # existing escape shortcut
        on_edit_code_block=trigger_edit_code_block,  # new Cmd/Ctrl+E
    )

    # -------------------------
    # Chat share selection
    # -------------------------
    CHAT_ICON_INACTIVE_COLOR = ft.Colors.PRIMARY
    CHAT_ICON_ACTIVE_COLOR = ft.Colors.GREEN_500
    chat_icon_btn_ref: list[ft.IconButton | None] = [None]

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
            text = get_value() or ""
            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError("Graph JSON must be a single object at the root")
            base = graph_ref[0]
            if base is not None:
                base_dump = base.model_dump(by_alias=True)
                for key in MERGE_GRAPH_KEYS_IF_MISSING:
                    if key not in data:
                        data[key] = base_dump.get(key)
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
