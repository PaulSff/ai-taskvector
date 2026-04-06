"""
Code editor for workflow graph JSON: uses flet-code-editor when available (syntax highlighting),
otherwise falls back to a plain multiline TextField. Shared by workflow inline code view and dialogs.
Find/replace is provided by the code editor (e.g. flet-code-editor).

Set FLET_PLAIN_CODE_EDITOR=1 to force the plain TextField (avoids "Unknown control: CodeEditor"
if the extension is not loaded by the Flet client).

Use format_json_for_editor() when loading graph (or other) data into the editor so non-ASCII text
is shown as real characters (json.dumps defaults to ASCII-only escapes).
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable

import flet as ft


def get_code_language(lang: str) -> str:
    # map common names to flet-code-editor CodeLanguage keys (falls back to JSON)
    if not lang:
        return "TEXT"
    k = lang.strip().lower()
    if k in ("py", "python"):
        return "PYTHON"
    if k in ("js", "javascript"):
        return "JAVASCRIPT"
    if k in ("ts", "typescript"):
        return "TYPESCRIPT"
    if k in ("html",):
        return "HTML"
    if k in ("css",):
        return "CSS"
    return k.upper()

def format_json_for_editor(data: Any, *, indent: int = 2) -> str:
    """
    Serialize JSON for display in code editors:
    - ensure_ascii=False so Unicode shows as real chars
    - if top-level contains code_blocks (list of objects with id, language, source),
      leave each source as a raw multiline string (no extra escaping) and keep JSON pretty.
    """
    # If structure contains code_blocks with 'source', ensure source is a str (no escaping)
    def _prepare(obj):
        if isinstance(obj, dict):
            # shallow copy to avoid mutating original
            new = {}
            for k, v in obj.items():
                if k == "code_blocks" and isinstance(v, list):
                    new_list = []
                    for item in v:
                        if isinstance(item, dict) and "source" in item and isinstance(item["source"], str):
                            # keep source exactly as-is (no further processing)
                            new_item = dict(item)
                            new_item["source"] = item["source"]
                            new_list.append(new_item)
                        else:
                            new_list.append(_prepare(item))
                    new[k] = new_list
                else:
                    new[k] = _prepare(v)
            return new
        elif isinstance(obj, list):
            return [_prepare(i) for i in obj]
        else:
            return obj

    prepared = _prepare(data)
    # json.dumps with ensure_ascii=False preserves Unicode; keep separators for readability
    return json.dumps(prepared, indent=indent, ensure_ascii=False, default=str)


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
    page: ft.Page | None = None,
    language: str = "json",
) -> tuple[
    ft.Control,
    Callable[[], str],
    Callable[[], None],
    Callable[[], None],
    Callable[[], tuple[int, int] | None],
]:
    """
    Build an editable code field (syntax-highlighted when flet-code-editor is installed).
    Returns (control, get_value, show_find_bar, hide_find_bar, get_selection_range).
    get_selection_range() returns (start, end) for a non-empty selection, else None.
    show_find_bar and hide_find_bar are no-ops (find/replace is provided by the code editor).
    height/width: optional dimensions. expand: use for flexible layout (e.g. workflow tab).
    page: optional, for compatibility (unused).
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
            # prefer explicit language string if supplied in 'language' param (e.g., "python")
            # fall back to JSON for the main editor
            mapped = getattr(CodeLanguage, language.upper(), None) or getattr(CodeLanguage, get_code_language(language), None)
            code_lang = mapped or getattr(CodeLanguage, "JSON", None)
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
        # Read from the actual editable control so Apply always gets current content
        # (e.g. when code_editor is a Container around flet-code-editor, it has no .value)
        ctrl = _editable_ref[0] if _editable_ref else code_editor
        v = getattr(ctrl, "value", None)
        return (v if v is not None else text_ref[0])

    def get_selection_range() -> tuple[int, int] | None:
        ctrl = _editable_ref[0] if _editable_ref else None
        if ctrl is None:
            return None
        sel = getattr(ctrl, "selection", None)
        if sel is None:
            return None
        start, end = sel.start, sel.end
        if start >= end:
            return None
        return (start, end)

    # Find/replace is provided by the code editor (e.g. flet-code-editor); no custom bar.
    return code_editor, get_value, lambda: None, lambda: None, get_selection_range


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
            # prefer explicit language string if supplied in 'language' param (e.g., "python")
            # fall back to JSON for the main editor
            mapped = getattr(CodeLanguage, language.upper(), None) or getattr(CodeLanguage, get_code_language(language), None)
            code_lang = mapped or getattr(CodeLanguage, "JSON", None)
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
