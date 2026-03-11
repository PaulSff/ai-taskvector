"""
Code editor for workflow graph JSON: uses flet-code-editor when available (syntax highlighting),
otherwise falls back to a plain multiline TextField. Shared by workflow inline code view and dialogs.
Supports optional find and find & replace toolbar.

Set FLET_PLAIN_CODE_EDITOR=1 to force the plain TextField (avoids "Unknown control: CodeEditor"
if the extension is not loaded by the Flet client).
"""
from __future__ import annotations

import os
from typing import Callable

import flet as ft

# Surrounding: padding/border area around the whole code editor (find bar + body).
CODE_EDITOR_BG = "#0d1117"  # GitHub dark
# Body: the actual text/code area where you type.
CODE_EDITOR_BODY_BG = "#0d1117"  # slightly lighter than surrounding (GitHub dark softer)
# Other nice dark options for body:
# CODE_EDITOR_BODY_BG = "#1a1b26"   # Tokyo Night
# CODE_EDITOR_BODY_BG = "#282c34"   # One Dark (Atom)
# CODE_EDITOR_BODY_BG = "#0c0e14"   # Deep black-blue
# CODE_EDITOR_BODY_BG = "#1e1e2e"   # Catppuccin Mocha base

# Optional: syntax-highlighting code editor (https://pypi.org/project/flet-code-editor/)
# Use plain editor if env requests it (avoids "Unknown control" when extension not loaded)
_USE_PLAIN = os.environ.get("FLET_PLAIN_CODE_EDITOR", "").strip() in ("1", "true", "yes")
if _USE_PLAIN:
    fce = None
    _HAS_FCE = False
else:
    try:
        import flet_code_editor as fce
        _HAS_FCE = True
    except ImportError:
        fce = None
        _HAS_FCE = False


def build_code_editor(
    code: str = "",
    *,
    height: int | None = None,
    width: int | None = None,
    expand: bool = False,
    find_replace: bool = True,
    page: ft.Page | None = None,
    language: str = "json",
) -> tuple[ft.Control, Callable[[], str], Callable[[], None], Callable[[], None]]:
    """
    Build an editable code field (syntax-highlighted when flet-code-editor is installed).
    Returns (control, get_value, show_find_bar, hide_find_bar). Use get_value() to read current text.
    show_find_bar: call to open the find/replace bar (hidden by default; e.g. on Ctrl+F).
    hide_find_bar: call to close it (e.g. on Escape).
    height/width: optional dimensions. expand: use for flexible layout (e.g. workflow tab).
    find_replace: if True, add a find/replace bar (hidden by default).
    page: optional, for "Not found" snackbar and updates when find_replace is True.
    language: syntax language when using flet-code-editor ("json", "python", etc.).
    """
    text_ref: list[str] = [code]

    if _HAS_FCE and fce is not None:
        # Use flet-code-editor for syntax highlighting (JSON for graph editing)
        CodeLanguage = getattr(fce, "CodeLanguage", None)
        CustomCodeTheme = getattr(fce, "CustomCodeTheme", None)
        CodeTheme = getattr(fce, "CodeTheme", None)
        code_lang = None
        if CodeLanguage is not None:
            code_lang = getattr(CodeLanguage, language.upper(), None) or getattr(CodeLanguage, "JSON", None)
        # Use CustomCodeTheme with root.bgcolor so the editor body uses CODE_EDITOR_BODY_BG
        theme = None
        if CustomCodeTheme is not None:
            try:
                theme = CustomCodeTheme(
                    root=ft.TextStyle(
                        bgcolor=CODE_EDITOR_BODY_BG,
                        color=ft.Colors.GREY_200,
                        font_family="monospace",
                        size=13,
                    ),
                    keyword=ft.TextStyle(color=ft.Colors.PURPLE_200),
                    string=ft.TextStyle(color=ft.Colors.GREEN_200),
                    number=ft.TextStyle(color=ft.Colors.AMBER_200),
                    comment=ft.TextStyle(color=ft.Colors.GREY_500, italic=True),
                    name=ft.TextStyle(color=ft.Colors.CYAN_200),
                )
            except Exception:
                theme = None
        if theme is None and CodeTheme is not None:
            theme = getattr(CodeTheme, "MONOKAI_SUBLIME", None) or getattr(CodeTheme, "ATOM_ONE_DARK", None)
        kwargs = {
            "value": code,
            "expand": expand,
            "read_only": False,
            "text_style": ft.TextStyle(font_family="monospace", size=13),
        }
        if code_lang is not None:
            kwargs["language"] = code_lang
        if theme is not None:
            kwargs["code_theme"] = theme
        inner_editor = fce.CodeEditor(**kwargs)
        if height is not None:
            inner_editor.height = height
        if width is not None:
            inner_editor.width = width

        def _on_fce_change(e: ft.ControlEvent) -> None:
            text_ref[0] = (e.control.value if e.control.value is not None else "") or ""

        inner_editor.on_change = _on_fce_change
        code_editor = ft.Container(
            content=inner_editor,
            border_radius=4,
            expand=expand,
        )
        _editable_ref: list[ft.Control] = [inner_editor]
    else:
        # Fallback: plain TextField (body background matches CODE_EDITOR_BODY_BG)
        code_editor = ft.TextField(
            value=code,
            multiline=True,
            expand=expand,
            bgcolor=CODE_EDITOR_BODY_BG,
            text_style=ft.TextStyle(font_family="monospace", size=13),
            border=ft.InputBorder.NONE,
            content_padding=ft.Padding.all(12),
            cursor_color=ft.Colors.CYAN_200,
        )
        if height is not None:
            code_editor.height = height
        if width is not None:
            code_editor.width = width

        def _on_tf_change(e: ft.ControlEvent) -> None:
            text_ref[0] = e.control.value if e.control.value is not None else ""

        code_editor.on_change = _on_tf_change
        _editable_ref: list[ft.Control] = [code_editor]

    def get_value() -> str:
        v = getattr(code_editor, "value", None)
        return (v if v is not None else text_ref[0])

    if not find_replace:
        return code_editor, get_value, lambda: None, lambda: None

    find_start_ref: list[int] = [0]
    last_match_ref: list[tuple[int, int] | None] = [None]

    def _on_find_tf_change(_e: ft.ControlEvent) -> None:
        find_start_ref[0] = 0

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
        return text_ref[0]

    async def _select_range(start: int, end: int) -> None:
        ctrl = _editable_ref[0] if _editable_ref else code_editor
        if hasattr(ctrl, "selection"):
            ctrl.selection = ft.TextSelection(base_offset=start, extent_offset=end)
        await ctrl.focus_async()
        ctrl.update()
        if page:
            page.update()

    def _set_editor_value(new_text: str) -> None:
        text_ref[0] = new_text
        ctrl = _editable_ref[0] if _editable_ref else code_editor
        if hasattr(ctrl, "value"):
            ctrl.value = new_text
        ctrl.update()
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
        search_until = len(text) if start_from <= 0 else start_from
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
        _set_editor_value(new_text)
        new_end = start + len(repl)
        await _select_range(start, new_end)
        find_start_ref[0] = new_end
        last_match_ref[0] = None

    def _on_replace_all(_e: ft.ControlEvent) -> None:
        needle = find_tf.value or ""
        repl = replace_tf.value or ""
        if not needle:
            return
        text = _get_text()
        lower = text.lower()
        needle_lower = needle.lower()
        result = []
        i = 0
        count = 0
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
        _set_editor_value("".join(result))
        find_start_ref[0] = 0
        last_match_ref[0] = None
        if page:
            page.snack_bar = ft.SnackBar(content=ft.Text(f"Replaced {count} occurrence(s)"), open=True)
            page.update()

    find_row = ft.Row(
        [
            find_tf,
            ft.IconButton(icon=ft.Icons.ARROW_UPWARD, icon_size=18, tooltip="Previous", on_click=_on_find_prev),
            ft.IconButton(icon=ft.Icons.ARROW_DOWNWARD, icon_size=18, tooltip="Next", on_click=_on_find_next),
        ],
        spacing=6,
        alignment=ft.MainAxisAlignment.START,
    )
    replace_row = ft.Row(
        [
            replace_tf,
            ft.IconButton(icon=ft.Icons.FIND_REPLACE, icon_size=18, tooltip="Replace", on_click=_on_replace),
            ft.IconButton(icon=ft.Icons.REPEAT, icon_size=18, tooltip="Replace all", on_click=_on_replace_all),
        ],
        spacing=6,
        alignment=ft.MainAxisAlignment.START,
    )

    find_bar_container_ref: list[ft.Container] = []

    def show_find_bar() -> None:
        if find_bar_container_ref:
            find_bar_container_ref[0].visible = True
            find_bar_container_ref[0].update()
        if page:
            page.update()

    def hide_find_bar() -> None:
        if find_bar_container_ref:
            find_bar_container_ref[0].visible = False
            find_bar_container_ref[0].update()
        if page:
            page.update()

    find_bar_container = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Row([find_row, replace_row], spacing=12),
                        ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, tooltip="Close (Esc)", on_click=lambda _: hide_find_bar()),
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
    find_bar_container_ref.append(find_bar_container)

    column = ft.Column(
        [find_bar_container, code_editor],
        spacing=6,
        expand=expand,
    )
    wrapper = ft.Container(
        content=column,
        bgcolor=CODE_EDITOR_BG,
        border_radius=6,
        padding=12,
        expand=expand,
    )
    return wrapper, get_value, show_find_bar, hide_find_bar


def build_code_display(
    code: str = "",
    *,
    language: str = "json",
    height: int | None = None,
    width: int | None = None,
    expand: bool = False,
    page: ft.Page | None = None,
) -> tuple[ft.Control, Callable[[str], None], Callable[[int | None], None]]:
    """
    Build a read-only code display with the same syntax highlighting as the editor.
    Returns (control, set_value, set_height). set_value(new_text) updates content; set_height(h) sets inner height (for collapse/expand).
    """
    text_ref: list[str] = [code]

    def set_value(new_text: str) -> None:
        text_ref[0] = new_text
        if display_ref and display_ref[0]:
            ctrl = display_ref[0]
            if hasattr(ctrl, "value"):
                ctrl.value = new_text
            try:
                ctrl.update()
                if page:
                    page.update()
            except Exception:
                pass

    def set_height(h: int | None) -> None:
        if display_ref and display_ref[0]:
            ctrl = display_ref[0]
            if hasattr(ctrl, "height"):
                ctrl.height = h
            try:
                ctrl.update()
                if page:
                    page.update()
            except Exception:
                pass

    display_ref: list[ft.Control] = []

    if _HAS_FCE and fce is not None:
        CodeLanguage = getattr(fce, "CodeLanguage", None)
        CustomCodeTheme = getattr(fce, "CustomCodeTheme", None)
        CodeTheme = getattr(fce, "CodeTheme", None)
        code_lang = None
        if CodeLanguage is not None:
            code_lang = getattr(CodeLanguage, language.upper(), None) or getattr(CodeLanguage, "JSON", None)
        theme = None
        if CustomCodeTheme is not None:
            try:
                theme = CustomCodeTheme(
                    root=ft.TextStyle(
                        bgcolor=CODE_EDITOR_BODY_BG,
                        color=ft.Colors.GREY_200,
                        font_family="monospace",
                        size=13,
                    ),
                    keyword=ft.TextStyle(color=ft.Colors.PURPLE_200),
                    string=ft.TextStyle(color=ft.Colors.GREEN_200),
                    number=ft.TextStyle(color=ft.Colors.AMBER_200),
                    comment=ft.TextStyle(color=ft.Colors.GREY_500, italic=True),
                    name=ft.TextStyle(color=ft.Colors.CYAN_200),
                )
            except Exception:
                theme = None
        if theme is None and CodeTheme is not None:
            theme = getattr(CodeTheme, "MONOKAI_SUBLIME", None) or getattr(CodeTheme, "ATOM_ONE_DARK", None)
        kwargs = {
            "value": code,
            "expand": expand,
            "read_only": True,
            "text_style": ft.TextStyle(font_family="monospace", size=13),
        }
        if code_lang is not None:
            kwargs["language"] = code_lang
        if theme is not None:
            kwargs["code_theme"] = theme
        inner = fce.CodeEditor(**kwargs)
        if height is not None:
            inner.height = height
        if width is not None:
            inner.width = width
        display_ref.append(inner)
        control = ft.Container(
            content=inner,
            bgcolor=CODE_EDITOR_BG,
            border_radius=4,
            expand=expand,
        )
    else:
        inner = ft.TextField(
            value=code,
            multiline=True,
            read_only=True,
            expand=expand,
            bgcolor=CODE_EDITOR_BODY_BG,
            text_style=ft.TextStyle(font_family="monospace", size=13),
            border=ft.InputBorder.NONE,
            content_padding=ft.Padding.all(12),
        )
        if height is not None:
            inner.height = height
        if width is not None:
            inner.width = width
        display_ref.append(inner)
        control = ft.Container(
            content=inner,
            bgcolor=CODE_EDITOR_BG,
            border_radius=4,
            expand=expand,
        )

    return control, set_value, set_height
