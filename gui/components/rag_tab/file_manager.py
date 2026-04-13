"""
RAG tab: list files under mydata_dir (My documents view).
"""
from __future__ import annotations

from typing import Callable

import flet as ft

from gui.components.settings import get_mydata_dir


def build_rag_file_manager_panel() -> tuple[ft.Container, Callable[[], None]]:
    """
    Build the file-manager view and a ``refresh()`` that repopulates the list from disk.
    """
    files_scroll = ft.Column(
        [],
        spacing=4,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    def refresh_file_manager() -> None:
        root = get_mydata_dir()
        rows: list[ft.Control] = []
        try:
            if not root.exists():
                rows.append(ft.Text("The mydata folder does not exist yet.", size=12, color=ft.Colors.GREY_500))
            else:
                paths = sorted(p for p in root.rglob("*") if p.is_file())
                if not paths:
                    rows.append(ft.Text("No files in mydata.", size=12, color=ft.Colors.GREY_500))
                else:
                    for p in paths:
                        rel = p.relative_to(root)
                        rows.append(ft.Text(str(rel), size=12, font_family="monospace", selectable=True))
        except OSError as ex:
            rows.append(ft.Text(f"Error listing mydata: {ex}", size=12, color=ft.Colors.ERROR))
        files_scroll.controls = rows
        try:
            files_scroll.update()
        except Exception:
            pass

    content = ft.Container(
        content=ft.Column(
            [
                ft.Text("My documents", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_300),
                ft.Text("Files stored under mydata (uploaded or saved here).", size=11, color=ft.Colors.GREY_500),
                ft.Container(height=8),
                ft.Container(content=files_scroll, expand=True),
            ],
            expand=True,
            spacing=6,
        ),
        padding=24,
        expand=True,
    )
    return content, refresh_file_manager
