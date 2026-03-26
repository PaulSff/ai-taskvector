from __future__ import annotations

import asyncio
from typing import Any, Callable, Literal

import flet as ft


FocusSlot = Literal["first", "bottom"]


class ChatFocusHandler:
    """Tracks preferred input focus and restores it after resize/stop transitions."""

    def __init__(
        self,
        *,
        page: ft.Page,
        first_field: ft.TextField,
        bottom_field: ft.TextField,
        is_busy: Callable[[], bool],
    ) -> None:
        self._page = page
        self._first_field = first_field
        self._bottom_field = bottom_field
        self._is_busy = is_busy
        self._pref: FocusSlot | None = None

    def mark_first(self) -> None:
        self._pref = "first"

    def mark_bottom(self) -> None:
        self._pref = "bottom"

    def set_preference(self, which: FocusSlot | None) -> None:
        self._pref = which

    def schedule_restore(self) -> None:
        if self._is_busy():
            return
        which = self._pref
        if which == "bottom":
            async def _focus_bottom() -> None:
                await self._focus_field(self._bottom_field)

            self._page.run_task(_focus_bottom)
        elif which == "first":
            async def _focus_first() -> None:
                await self._focus_field(self._first_field)

            self._page.run_task(_focus_first)

    def install_resize_restore(self) -> None:
        prev_on_resize = self._page.on_resize

        def _on_resize(e: Any) -> None:
            try:
                if callable(prev_on_resize):
                    prev_on_resize(e)
            except Exception:
                pass
            self.schedule_restore()

        self._page.on_resize = _on_resize

    async def _focus_field(self, field: ft.TextField) -> None:
        # Retry focus a few times; resizes/layout changes can drop focus.
        for delay_s in (0.0, 0.05, 0.2, 0.5):
            try:
                await asyncio.sleep(delay_s)
                await field.focus()
                return
            except Exception:
                continue
