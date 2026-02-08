"""
Simple multiline code editor (plain TextField, monospace).
Shared by workflow inline code view and dialogs (e.g. view graph JSON).
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
) -> tuple[ft.Control, Callable[[], str]]:
    """
    Build an editable code/text field (monospace, no border).
    Returns (control, get_value). Use get_value() to read current text.
    height/width: optional dimensions. expand: use for flexible layout (e.g. workflow tab).
    """
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

    def get_value() -> str:
        return code_tf.value if code_tf.value is not None else code

    return code_tf, get_value
