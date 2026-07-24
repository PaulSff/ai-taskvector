from __future__ import annotations

import asyncio
import inspect
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

    # ------------------------------------------------------------------
    # Focus preference management
    # ------------------------------------------------------------------

    def mark_first(self) -> None:
        self._pref = "first"

    def mark_bottom(self) -> None:
        self._pref = "bottom"

    def set_preference(self, which: FocusSlot | None) -> None:
        self._pref = which

    # ------------------------------------------------------------------
    # Focus restore
    # ------------------------------------------------------------------

    def schedule_restore(self) -> None:
        """Restore focus to the preferred field if UI is not busy."""
        if self._is_busy():
            return

        if self._pref == "bottom":

            async def _focus_bottom() -> None:
                await self._focus_field(self._bottom_field)

            self._page.run_task(_focus_bottom)

        elif self._pref == "first":

            async def _focus_first() -> None:
                await self._focus_field(self._first_field)

            self._page.run_task(_focus_first)

    # ------------------------------------------------------------------
    # Resize handling
    # ------------------------------------------------------------------

    def install_resize_restore(self) -> None:
        """Wrap existing resize handler and restore focus afterward."""
        prev_on_resize = self._page.on_resize

        def _on_resize(e: Any) -> None:
            # Safely call previous resize handler.
            if callable(prev_on_resize):
                try:
                    self._call_resize_handler(prev_on_resize, e)
                except Exception:
                    pass

            # Restore preferred focus after resize/layout updates.
            self.schedule_restore()

        self._page.on_resize = _on_resize

    def _call_resize_handler(
        self,
        handler: Callable[..., Any],
        event: Any,
    ) -> None:
        """
        Call resize handler safely.

        Some Flet handlers are defined as:
            def handler(e): ...
        while others are:
            def handler(): ...

        This avoids:
            Expected 0 positional arguments
        """
        try:
            sig = inspect.signature(handler)

            if len(sig.parameters) == 0:
                handler()
            else:
                handler(event)

        except (TypeError, ValueError):
            # Fallback if signature introspection fails.
            try:
                handler(event)
            except TypeError:
                handler()

    # ------------------------------------------------------------------
    # Internal focus helper
    # ------------------------------------------------------------------

    async def _focus_field(self, field: ft.TextField) -> None:
        """
        Retry focus a few times because resize/layout updates
        can temporarily steal focus.
        """
        for delay_s in (0.0, 0.05, 0.2, 0.5):
            try:
                await asyncio.sleep(delay_s)
                await field.focus()
                return
            except Exception:
                continue
