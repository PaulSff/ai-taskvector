"""
Reusable gesture/hover helpers for Flet controls.
Extracts event normalization and hover-detector wrapping so callers only handle (x, y) and exit.
"""
from __future__ import annotations

from typing import Callable

import flet as ft


def hover_local_xy(e: ft.PointerEvent) -> tuple[float, float]:
    """Get (local_x, local_y) from a hover/enter PointerEvent."""
    pos = e.local_position
    return (float(pos.x), float(pos.y))


def wrap_hover(
    content: ft.Control,
    on_hover_xy: Callable[[float, float], None],
    on_exit: Callable[[], None] | None = None,
    *,
    hover_interval: int = 30,
) -> ft.GestureDetector:
    """Wrap content in a GestureDetector that reports hover as (x, y) and calls on_exit when pointer leaves."""
    def on_hover(e: ft.PointerEvent) -> None:
        x, y = hover_local_xy(e)
        on_hover_xy(x, y)

    def on_exit_handler(e: ft.PointerEvent) -> None:
        if on_exit is not None:
            on_exit()

    return ft.GestureDetector(
        content=content,
        hover_interval=hover_interval,
        on_hover=on_hover,
        on_enter=on_hover,
        on_exit=on_exit_handler,
    )
