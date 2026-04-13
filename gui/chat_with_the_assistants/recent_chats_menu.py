from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft

from gui.chat_with_the_assistants.history_store import list_recent_chat_files
from gui.chat_with_the_assistants.ui_utils import safe_page_update, safe_update


def time_ago_short(delta_seconds: float) -> str:
    s = max(0, int(delta_seconds))
    if s < 60:
        return f"{s}s"
    m = s // 60
    if m < 60:
        return f"{m}m"
    h = m // 60
    if h < 24:
        return f"{h}h"
    d = h // 24
    if d < 7:
        return f"{d}d"
    w = d // 7
    if w < 52:
        return f"{w}w"
    y = w // 52
    return f"{y}y"


@dataclass
class RecentChatsMenu:
    """A compact click-to-open recent chats menu (top/bottom variants)."""

    page: ft.Page
    chat_history_dir: Path
    on_select: Callable[[Path], None]
    limit: int = 3

    color: str = ft.Colors.GREY_400
    font_size: int = 11
    item_height: int = 32
    arrow_size: int = 14

    selected_filename: str | None = None

    recent_label_top: ft.Text | None = None
    recent_label_bottom: ft.Text | None = None
    menu_top: ft.PopupMenuButton | None = None
    menu_bottom: ft.PopupMenuButton | None = None
    row_top: ft.Row | None = None
    row_bottom: ft.Row | None = None

    def build(self) -> "RecentChatsMenu":
        self.recent_label_top = ft.Text("Recent chats", size=self.font_size, color=self.color)
        self.recent_label_bottom = ft.Text("Recent chats", size=self.font_size, color=self.color)

        self.menu_top = ft.PopupMenuButton(
            content=ft.Row(
                [
                    self.recent_label_top,
                    ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=self.arrow_size, color=self.color),
                ],
                spacing=2,
            ),
            items=[],
            menu_position=ft.PopupMenuPosition.UNDER,
            padding=0,
        )
        self.menu_bottom = ft.PopupMenuButton(
            content=ft.Row(
                [
                    self.recent_label_bottom,
                    ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=self.arrow_size, color=self.color),
                ],
                spacing=2,
            ),
            items=[],
            menu_position=ft.PopupMenuPosition.UNDER,
            padding=0,
        )

        self.row_top = ft.Row([self.menu_top], spacing=0, visible=True)
        self.row_bottom = ft.Row([self.menu_bottom], spacing=0, visible=False)
        return self

    def set_phase(self, *, has_sent_any: bool) -> None:
        """Toggle which row is visible (top composer vs bottom composer)."""
        if self.row_top is None or self.row_bottom is None:
            return
        self.row_top.visible = not has_sent_any
        self.row_bottom.visible = has_sent_any
        safe_update(self.row_top, self.row_bottom)
        safe_page_update(self.page)

    def set_selected(self, filename: str | None) -> None:
        self.selected_filename = filename
        label = Path(filename).stem if filename else "Recent chats"
        if self.recent_label_top is not None:
            self.recent_label_top.value = label
        if self.recent_label_bottom is not None:
            self.recent_label_bottom.value = label
        safe_update(self.recent_label_top, self.recent_label_bottom)

    def refresh(self) -> None:
        if self.menu_top is None or self.menu_bottom is None:
            return
        files = list_recent_chat_files(self.chat_history_dir, limit=self.limit)
        file_map: dict[str, Path] = {p.name: p for p in files}

        items: list[ft.PopupMenuItem] = []
        if not file_map:
            items.append(
                ft.PopupMenuItem(
                    content=ft.Text("No chats yet", size=self.font_size, color=ft.Colors.GREY_500),
                    height=self.item_height,
                    padding=ft.Padding.symmetric(horizontal=10),
                )
            )
        else:
            now = time.time()
            for name, p in file_map.items():
                try:
                    age_s = now - p.stat().st_mtime
                except OSError:
                    age_s = 0
                age_txt = time_ago_short(age_s)
                item = ft.PopupMenuItem(
                    content=ft.Row(
                        [
                            ft.Text(Path(name).stem, size=self.font_size),
                            ft.Container(expand=True),
                            ft.Text(age_txt, size=self.font_size, color=ft.Colors.GREY_500),
                        ],
                        spacing=6,
                    ),
                    height=self.item_height,
                    padding=ft.Padding.symmetric(horizontal=10),
                )
                item.on_click = (lambda _e, _p=p: self.on_select(_p))
                items.append(item)

        self.menu_top.items = items
        self.menu_bottom.items = items

        # If selection disappeared, clear it.
        if self.selected_filename and self.selected_filename not in file_map:
            self.set_selected(None)

        safe_update(self.menu_top, self.menu_bottom)

