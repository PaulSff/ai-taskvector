"""
Simple multiline code editor (plain TextField, monospace).
Shared by workflow inline code view and dialogs (e.g. view graph JSON).
Supports optional find and find & replace toolbar.
"""
from __future__ import annotations

from typing import Callable

import flet as ft


def build_code_editor(
    code: str = "",
    *,
    height: int | None = None,
    width: int | None = None,
    expand: bool = False,
    find_replace: bool = True,
    page: ft.Page | None = None,
) -> tuple[ft.Control, Callable[[], str], Callable[[], None], Callable[[], None]]:
    """
    Build an editable code/text field (monospace, no border).
    Returns (control, get_value, show_find_bar, hide_find_bar). Use get_value() to read current text.
    show_find_bar: call to open the find/replace bar (hidden by default; e.g. on Ctrl+F).
    hide_find_bar: call to close it (e.g. on Escape).
    height/width: optional dimensions. expand: use for flexible layout (e.g. workflow tab).
    find_replace: if True, add a find/replace bar (hidden by default).
    page: optional, for "Not found" snackbar and updates when find_replace is True.
    """
    # Keep editor content in a ref so find/replace always searches latest (client may not sync value until focus change)
    text_ref: list[str] = [code]

    code_tf = ft.TextField(
        value=code,
        multiline=True,
        expand=expand,
        text_style=ft.TextStyle(font_family="monospace", size=13),
        border=ft.InputBorder.NONE,
        content_padding=ft.Padding.all(12),
        cursor_color=ft.Colors.CYAN_200,
    )
    if height is not None:
        code_tf.height = height
    if width is not None:
        code_tf.width = width

    def _on_code_change(e: ft.ControlEvent) -> None:
        text_ref[0] = e.control.value if e.control.value is not None else ""

    code_tf.on_change = _on_code_change

    def get_value() -> str:
        # Prefer control value; fall back to ref (ref is updated on every change so find uses latest)
        v = code_tf.value
        return v if v is not None else text_ref[0]

    if not find_replace:
        return code_tf, get_value, lambda: None, lambda: None

    # Find/replace state: [next search start index, last match (start, end) for Replace]
    find_start_ref: list[int] = [0]
    last_match_ref: list[tuple[int, int] | None] = [None]

    def _on_find_tf_change(_e: ft.ControlEvent) -> None:
        find_start_ref[0] = 0  # New search term: start from beginning

    async def _on_find_submit(_e: ft.ControlEvent) -> None:
        await _find_next()

    find_tf = ft.TextField(
        hint_text="Find",
        dense=True,
        width=180,
        height=36,
        text_style=ft.TextStyle(size=12),
        on_change=_on_find_tf_change,
        on_submit=_on_find_submit,
    )
    replace_tf = ft.TextField(
        hint_text="Replace",
        dense=True,
        width=180,
        height=36,
        text_style=ft.TextStyle(size=12),
    )

    def _get_text() -> str:
        # Use ref so we search the same content the user sees (updated on every editor change)
        return text_ref[0]

    async def _select_range(start: int, end: int) -> None:
        code_tf.selection = ft.TextSelection(base_offset=start, extent_offset=end)
        await code_tf.focus()
        code_tf.update()
        if page:
            page.update()

    async def _find_next() -> bool:
        needle = find_tf.value or ""
        if not needle:
            return False
        text = _get_text()
        haystack = text.lower()
        needle_lower = needle.lower()
        start_from = find_start_ref[0]
        pos = haystack.find(needle_lower, start_from)
        if pos < 0 and start_from > 0:
            pos = haystack.find(needle_lower, 0)
        if pos < 0:
            if page:
                page.snack_bar = ft.SnackBar(content=ft.Text("Not found"), open=True)
                page.update()
            return False
        end = pos + len(needle)
        await _select_range(pos, end)
        find_start_ref[0] = end
        last_match_ref[0] = (pos, end)
        return True

    async def _find_prev() -> bool:
        needle = find_tf.value or ""
        if not needle:
            return False
        text = _get_text()
        haystack = text.lower()
        needle_lower = needle.lower()
        start_from = find_start_ref[0]
        # Search before start_from (rfind in text[0:start_from])
        if start_from <= 0:
            search_until = len(text)
        else:
            search_until = start_from
        pos = haystack.rfind(needle_lower, 0, search_until)
        if pos < 0 and search_until == start_from:
            pos = haystack.rfind(needle_lower, 0, len(text))
        if pos < 0:
            if page:
                page.snack_bar = ft.SnackBar(content=ft.Text("Not found"), open=True)
                page.update()
            return False
        end = pos + len(needle)
        await _select_range(pos, end)
        find_start_ref[0] = pos
        last_match_ref[0] = (pos, end)
        return True

    async def _on_find_next(_e: ft.ControlEvent) -> None:
        await _find_next()

    async def _on_find_prev(_e: ft.ControlEvent) -> None:
        await _find_prev()

    async def _on_replace(_e: ft.ControlEvent) -> None:
        repl = replace_tf.value or ""
        text = _get_text()
        match = last_match_ref[0]
        if match is None:
            if not await _find_next():
                return
            match = last_match_ref[0]
        if match is None:
            return
        start, end = match
        new_text = text[:start] + repl + text[end:]
        code_tf.value = new_text
        text_ref[0] = new_text
        new_end = start + len(repl)
        await _select_range(start, new_end)
        find_start_ref[0] = new_end
        last_match_ref[0] = None
        code_tf.update()

    def _on_replace_all(_e: ft.ControlEvent) -> None:
        needle = find_tf.value or ""
        repl = replace_tf.value or ""
        if not needle:
            return
        text = _get_text()
        # Case-insensitive replace: we replace all occurrences of needle (case-insensitive)
        # by building result manually to preserve case of first occurrence per match if desired.
        # Simple approach: replace all (case-sensitive) first; or use regex for case-insensitive.
        count = 0
        lower = text.lower()
        needle_lower = needle.lower()
        result = []
        i = 0
        while i <= len(text):
            pos = lower.find(needle_lower, i)
            if pos < 0:
                result.append(text[i:])
                break
            result.append(text[i:pos])
            result.append(repl)
            count += 1
            i = pos + len(needle)
        if count == 0:
            if page:
                page.snack_bar = ft.SnackBar(content=ft.Text("Not found"), open=True)
                page.update()
            return
        code_tf.value = "".join(result)
        find_start_ref[0] = 0
        last_match_ref[0] = None
        code_tf.update()
        if page:
            page.snack_bar = ft.SnackBar(content=ft.Text(f"Replaced {count} occurrence(s)"), open=True)
            page.update()

    find_row = ft.Row(
        [
            find_tf,
            ft.IconButton(
                icon=ft.Icons.ARROW_UPWARD,
                icon_size=18,
                tooltip="Previous",
                on_click=_on_find_prev,
            ),
            ft.IconButton(
                icon=ft.Icons.ARROW_DOWNWARD,
                icon_size=18,
                tooltip="Next",
                on_click=_on_find_next,
            ),
        ],
        spacing=6,
        alignment=ft.MainAxisAlignment.START,
    )
    replace_row = ft.Row(
        [
            replace_tf,
            ft.IconButton(
                icon=ft.Icons.FIND_REPLACE,
                icon_size=18,
                tooltip="Replace",
                on_click=_on_replace,
            ),
            ft.IconButton(
                icon=ft.Icons.REPEAT,
                icon_size=18,
                tooltip="Replace all",
                on_click=_on_replace_all,
            ),
        ],
        spacing=6,
        alignment=ft.MainAxisAlignment.START,
    )

    find_bar_visible_ref: list[bool] = [False]

    def show_find_bar() -> None:
        find_bar_visible_ref[0] = True
        find_bar_container.visible = True
        find_bar_container.update()
        if page:
            page.update()

    def hide_find_bar() -> None:
        find_bar_visible_ref[0] = False
        find_bar_container.visible = False
        find_bar_container.update()
        if page:
            page.update()

    find_bar_container = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Row(
                            [find_row, replace_row],
                            spacing=12,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            icon_size=18,
                            tooltip="Close (Esc)",
                            on_click=lambda _: hide_find_bar(),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    spacing=8,
                ),
            ],
            spacing=4,
        ),
        visible=False,
        padding=ft.padding.symmetric(horizontal=8, vertical=6),
        bgcolor="#12161A",
        border_radius=6,
    )

    column = ft.Column(
        [
            find_bar_container,
            code_tf,
        ],
        spacing=6,
        expand=expand,
    )
    return column, get_value, show_find_bar, hide_find_bar
