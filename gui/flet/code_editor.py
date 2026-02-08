"""
Code view with syntax highlighting (JSON for workflow).
Based on: real-time code editor with regex-based highlighting
(https://medium.com/@edoardobalducci/creating-a-real-time-code-editor-with-syntax-highlighting-with-flet-ac62834da2cf)
"""
from __future__ import annotations

import re
from typing import Callable

import flet as ft


# ---- Theme (dark, JSON-friendly) ----
class JsonDarkTheme:
    key = "#9CDCFE"       # keys / property names
    string = "#CE9178"     # string values
    number = "#B5CEA8"     # numbers
    keyword = "#569CD6"    # true, false, null
    bracket = "#FFD700"    # { } [ ] : ,


# ---- Syntax rules: (regex_pattern, color) ----
def _json_syntax_rules(theme: JsonDarkTheme) -> dict[str, tuple[str, str]]:
    return {
        "string_double": (
            r'(?P<STR>"(?:[^"\\]|\\.)*")',
            theme.string,
        ),
        "keyword": (
            r"\b(?P<KW>true|false|null)\b",
            theme.keyword,
        ),
        "number": (
            r"\b(?P<NUM>-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)\b",
            theme.number,
        ),
        "key": (
            r'(?P<KEY>"(?:[^"\\]|\\.)*")\s*:',
            theme.key,
        ),
        "bracket": (
            r'(?P<BR>[{}\[\]:,])',
            theme.bracket,
        ),
    }


def _build_highlight_content(
    text: str,
    rules: dict[str, tuple[str, str]],
    font_family: str,
    font_size: int,
    height: int | None = None,
    inner_scroll: bool = True,
) -> ft.Control:
    """Build a Column of highlighted lines. If height is set, column is that height.
    If inner_scroll is False, column has no scrollbar (for use inside an outer scroll)."""
    lines = text.split("\n") if text else [""]
    line_widgets: list[ft.Control] = []
    for idx, line in enumerate(lines):
        parts: list[ft.Control] = []
        last_idx = 0
        matches: list[tuple[int, int, str, str]] = []

        for _name, (pattern, color) in rules.items():
            for m in re.finditer(pattern, line):
                start, end = m.span()
                matches.append((start, end, m.group(0), color))

        matches.sort(key=lambda x: (x[0], -x[1]))

        for start, end, matched_text, color in matches:
            if start >= last_idx:
                if start > last_idx:
                    plain = line[last_idx:start]
                    parts.append(
                        ft.Text(
                            plain,
                            font_family=font_family,
                            size=font_size,
                            no_wrap=False,
                        )
                    )
                parts.append(
                    ft.Text(
                        matched_text,
                        font_family=font_family,
                        size=font_size,
                        color=color,
                        no_wrap=False,
                    )
                )
                last_idx = end

        if last_idx < len(line):
            parts.append(
                ft.Text(
                    line[last_idx:],
                    font_family=font_family,
                    size=font_size,
                    no_wrap=False,
                )
            )

        line_num = ft.Container(
            content=ft.Text(
                f"{idx + 1}",
                color=ft.Colors.GREY_600,
                size=font_size,
                font_family=font_family,
            ),
            width=36,
            alignment=ft.Alignment.CENTER_RIGHT,
        )
        line_row = ft.Row(
            controls=[line_num] + parts,
            spacing=4,
            wrap=False,
        )
        line_widgets.append(line_row)

    col = ft.Column(
        controls=line_widgets,
        spacing=0,
        scroll=ft.ScrollMode.AUTO if inner_scroll else None,
    )
    if height is not None:
        col.height = height
    else:
        col.expand = True
    return col


def build_code_editor(
    code: str = "",
    *,
    read_only: bool = False,
    height: int = 400,
    width: int | None = None,
    font_family: str = "monospace",
    font_size: int = 12,
) -> tuple[ft.Control, Callable[[], str]]:
    """
    Simple editable code editor: one Column with one multiline TextField.
    width: optional width for the scrollable/editable area (the part where code is shown).
    Returns (control, get_value). Use get_value() to read current text.
    """
    if read_only:
        highlight = ft.Container(
            content=_build_highlight_content(
                code,
                _json_syntax_rules(JsonDarkTheme()),
                font_family,
                font_size,
                height=height,
                inner_scroll=False,
            ),
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border_radius=6,
            height=height,
        )
        if width is not None:
            highlight.width = width
        return highlight, lambda: code

    tf_kw: dict = {
        "value": code,
        "multiline": True,
        "min_lines": 1,
        "text_style": ft.TextStyle(
            font_family=font_family,
            size=font_size,
        ),
        "border_color": ft.Colors.GREY_700,
        "bgcolor": ft.Colors.SURFACE_CONTAINER_HIGHEST,
        "content_padding": 12,
        "height": height,
    }
    code_tf = ft.TextField(**tf_kw)
    # Wrap in Container with width so the scrollable/editable area is constrained
    editor_content: ft.Control = code_tf
    if width is not None:
        editor_content = ft.Container(
            content=code_tf,
            width=width,
            height=height,
        )
    column = ft.Column(
        controls=[editor_content],
        height=height,
    )

    def get_value() -> str:
        return code_tf.value if code_tf.value is not None else code

    return column, get_value


def build_workflow_code_view(
    initial_json: str = "{}",
) -> tuple[ft.Container, Callable[[str], None]]:
    """
    Build the code view with JSON syntax highlighting (read-only).
    Returns (container, set_value). Toggle container.visible to show/hide.
    Refresh content with set_value(json_string).
    """
    theme = JsonDarkTheme()
    rules = _json_syntax_rules(theme)
    font_family = "monospace"
    font_size = 12

    highlight_container = ft.Container(
        content=_build_highlight_content(initial_json, rules, font_family, font_size),
        expand=True,
        padding=ft.padding.symmetric(horizontal=12, vertical=8),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border_radius=6,
    )

    def set_value(text: str) -> None:
        highlight_container.content = _build_highlight_content(
            text, rules, font_family, font_size
        )
        highlight_container.update()

    container = ft.Container(
        content=ft.Column(
            [
                ft.Text("Raw JSON (read-only)", size=12, color=ft.Colors.GREY_500),
                highlight_container,
            ],
            expand=True,
        ),
        expand=True,
        visible=False,
    )
    return container, set_value


def build_workflow_code_dialog_content(
    initial_json: str = "{}",
) -> tuple[ft.Control, Callable[[str], None]]:
    """
    Build code view content for use inside a dialog (syntax-highlighted JSON).
    Returns (content_control, set_value). Give content a fixed height when placing in dialog.
    """
    theme = JsonDarkTheme()
    rules = _json_syntax_rules(theme)
    font_family = "monospace"
    font_size = 12

    highlight_container = ft.Container(
        content=_build_highlight_content(initial_json, rules, font_family, font_size),
        padding=ft.padding.symmetric(horizontal=12, vertical=8),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border_radius=6,
    )

    def set_value(text: str) -> None:
        highlight_container.content = _build_highlight_content(
            text, rules, font_family, font_size
        )
        highlight_container.update()

    content = ft.Container(
        content=ft.Column(
            [
                ft.Text("Workflow JSON (read-only)", size=12, color=ft.Colors.GREY_500),
                highlight_container,
            ],
            height=480,
            scroll=ft.ScrollMode.AUTO,
        ),
        width=600,
    )
    return content, set_value
