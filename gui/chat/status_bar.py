"""
Inline status bar: "Planning next moves…", "Applying edits…" with animated dots.

Shown below the most recent user message during LLM runs. UI-only; not persisted.
"""
from __future__ import annotations

import asyncio
from typing import Callable

import flet as ft


class StatusBarController:
    """Controller for the inline status row (status text)."""

    def __init__(
        self,
        page: ft.Page,
        messages_col: ft.Column,
        safe_update: Callable[..., None],
        safe_page_update: Callable[[ft.Page], None],
    ) -> None:
        self._page = page
        self._messages_col = messages_col
        self._safe_update = safe_update
        self._safe_page_update = safe_page_update

        self._row: ft.Row | None = None
        self._txt: ft.Text | None = None
        self._anim_token = 0
        self._anim_base: str | None = None

    def set_status(self, msg: str | None, *, flush: bool = True) -> None:
        """Set status message (e.g. 'Planning next moves…'). None clears the bar.

        If ``flush`` is False, only mutates controls; caller must ``update()`` the messages column
        (and page) in the same batch — avoids an extra client round-trip before the user bubble.
        """
        if not msg:
            self._anim_token += 1
            self._anim_base = None
            if self._row is not None and self._row in self._messages_col.controls:
                self._messages_col.controls.remove(self._row)
                self._row = None
                self._txt = None
                self._safe_update(self._messages_col)
                self._safe_page_update(self._page)
            return

        self._anim_token += 1
        my_token = self._anim_token
        base = str(msg).strip().rstrip(".").rstrip("…").rstrip()
        self._anim_base = base

        async def _animate() -> None:
            i = 0
            while True:
                if my_token != self._anim_token:
                    return
                if self._txt is None or not base:
                    return
                dots = "." * (i % 4)
                self._txt.value = f"{base}{dots}"
                self._safe_update(self._txt)
                self._safe_page_update(self._page)
                i += 1
                try:
                    await asyncio.sleep(0.35)
                except Exception:
                    return

        self._page.run_task(_animate)

        if self._row is None or self._txt is None:
            self._txt = ft.Text(base, size=11, color=ft.Colors.GREY_500, italic=True, no_wrap=False)
            bubble = ft.Container(
                content=self._txt,
                padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                border_radius=8,
                bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.WHITE),
                expand=True,
            )
            self._row = ft.Row(
                [
                    ft.Container(expand=True, content=bubble, padding=ft.Padding.only(left=12)),
                ],
                spacing=0,
            )
            self._messages_col.controls.append(self._row)

        self._txt.value = base
        if flush:
            self._safe_update(self._txt)
            self._safe_page_update(self._page)
