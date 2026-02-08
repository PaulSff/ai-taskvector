"""
Standard notification (toast) style for the Flet GUI.
Uses an overlay toast at top center, auto-dismiss after a short duration.
"""
from __future__ import annotations

import asyncio

import flet as ft


# Default style for all notifications
TOAST_TEXT_SIZE = 12
TOAST_TEXT_COLOR = ft.Colors.WHITE
TOAST_BG_COLOR = ft.Colors.GREY_700
TOAST_PADDING = ft.padding.symmetric(horizontal=12, vertical=6)
TOAST_BORDER_RADIUS = 6
TOAST_TOP_OFFSET = 20
TOAST_DURATION_S = 1.0


async def show_toast(
    page: ft.Page,
    message: str,
    *,
    duration_s: float = TOAST_DURATION_S,
) -> None:
    """
    Show a short notification at top center, then remove it after duration_s.
    Uses the standard overlay toast pattern (full-width top bar, centered content).
    """
    toast_content = ft.Container(
        content=ft.Text(message, size=TOAST_TEXT_SIZE, color=TOAST_TEXT_COLOR),
        bgcolor=TOAST_BG_COLOR,
        padding=TOAST_PADDING,
        border_radius=TOAST_BORDER_RADIUS,
    )
    top_bar = ft.Container(
        content=ft.Row(
            [ft.Container(content=toast_content, padding=ft.padding.only(top=TOAST_TOP_OFFSET))],
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        left=0,
        right=0,
        top=0,
    )
    toast = ft.Stack(
        expand=True,
        controls=[top_bar],
    )
    page.overlay.append(toast)
    page.update()
    await asyncio.sleep(duration_s)
    page.overlay.remove(toast)
    page.update()
