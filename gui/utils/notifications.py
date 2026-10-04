"""
Standard notification (toast) style for the Flet GUI.

Uses an overlay toast at the top center and automatically dismisses it
after a short duration.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import flet as ft

type ToastCallback = Callable[[str], Awaitable[None]]


# Default style for all notifications
TOAST_TEXT_SIZE = 12
TOAST_TEXT_COLOR = ft.Colors.WHITE
TOAST_BG_COLOR = ft.Colors.GREY_700
TOAST_PADDING = ft.Padding.symmetric(horizontal=12, vertical=6)
TOAST_BORDER_RADIUS = 6
TOAST_TOP_OFFSET = 20
TOAST_DURATION_S = 1.0


def _safe_update(page: ft.Page) -> bool:
    """
    Update the page if its session is still alive.

    Returns:
        True if the update succeeded.
        False if the Flet session was already destroyed.
    """
    try:
        page.update()
        return True
    except RuntimeError as exc:
        if "destroyed session" in str(exc):
            return False
        raise


async def show_toast(
    page: ft.Page,
    message: str,
    *,
    duration_s: float = TOAST_DURATION_S,
) -> None:
    """Show a temporary toast notification at the top center of the page."""
    toast_content = ft.Container(
        content=ft.Text(
            message,
            size=TOAST_TEXT_SIZE,
            color=TOAST_TEXT_COLOR,
        ),
        bgcolor=TOAST_BG_COLOR,
        padding=TOAST_PADDING,
        border_radius=TOAST_BORDER_RADIUS,
    )

    top_bar = ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=toast_content,
                    padding=ft.Padding.only(top=TOAST_TOP_OFFSET),
                )
            ],
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

    added = False

    try:
        page.overlay.append(toast)
        added = True

        if not _safe_update(page):
            return

        await asyncio.sleep(duration_s)

    finally:
        if added:
            try:
                if toast in page.overlay:
                    page.overlay.remove(toast)
                    _safe_update(page)

            except (RuntimeError, ValueError):
                # The page session may have been destroyed, or the toast
                # may already have been removed.
                pass
