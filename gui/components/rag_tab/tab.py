"""
RAG tab: toolbar + Search / file-manager views; upload dialog; optional dev preview.
"""
from __future__ import annotations

import asyncio
import shutil
from typing import Any

import flet as ft

from assistants.roles import WORKFLOW_DESIGNER_ROLE_ID
from gui.chat.rag_context import get_rag_context, get_rag_context_by_path
from gui.components.settings import get_rag_index_dir

from .dialog_upload_file import build_rag_upload_file_dialog
from .file_manager import build_rag_file_manager_panel
from .helpers import run_rag_index_update_async
from .search import build_rag_search_panel


def build_rag_tab(page: ft.Page, show_rag_preview: bool = False) -> ft.Control:
    """
    Build the RAG tab: toolbar + Search (default) or file-manager view; upload via dialog.
    When show_rag_preview is True (dev mode), show a RAG context preview section below the main area.
    """
    ACTIVE_TOOLBAR_ICON_COLOR = ft.Colors.GREY_200
    INACTIVE_TOOLBAR_ICON_COLOR = ft.Colors.GREY_600

    rag_view_mode: list[str] = ["search"]  # "search" | "files"

    def _toast(msg: str) -> None:
        page.snack_bar = ft.SnackBar(content=ft.Text(msg), open=True)
        page.update()

    search_content = build_rag_search_panel(page)
    file_manager_content, refresh_file_manager, refresh_file_manager_async = build_rag_file_manager_panel(page)

    def _on_upload_mydata_changed() -> None:
        refresh_file_manager(refresh_storage_chart=True)

    _, open_upload_dialog = build_rag_upload_file_dialog(
        page,
        toast=_toast,
        on_mydata_changed=_on_upload_mydata_changed,
    )

    async def _toolbar_run_index_async() -> None:
        await run_rag_index_update_async(page, _toast)
        await refresh_file_manager_async()

    def _update_click(_e: ft.ControlEvent) -> None:
        page.run_task(_toolbar_run_index_async)

    def _clear_click(_e: ft.ControlEvent) -> None:
        idx_dir = get_rag_index_dir()
        try:
            if idx_dir.exists():
                shutil.rmtree(idx_dir)
                _toast("RAG index cleared.")
            else:
                _toast("No index to clear.")
        except OSError as err:
            _toast(f"Error: {err}")
        page.update()
        if rag_view_mode[0] == "files":
            refresh_file_manager()

    rag_main_view = ft.Container(content=search_content, expand=True)

    def show_search_view(_e: ft.ControlEvent | None = None) -> None:
        rag_view_mode[0] = "search"
        rag_main_view.content = search_content
        search_mode_btn.icon_color = ACTIVE_TOOLBAR_ICON_COLOR
        files_mode_btn.icon_color = INACTIVE_TOOLBAR_ICON_COLOR
        try:
            rag_main_view.update()
            search_mode_btn.update()
            files_mode_btn.update()
        except Exception:
            pass
        page.update()

    def show_files_view(_e: ft.ControlEvent | None = None) -> None:
        rag_view_mode[0] = "files"
        rag_main_view.content = file_manager_content
        files_mode_btn.icon_color = ACTIVE_TOOLBAR_ICON_COLOR
        search_mode_btn.icon_color = INACTIVE_TOOLBAR_ICON_COLOR
        try:
            rag_main_view.update()
            search_mode_btn.update()
            files_mode_btn.update()
        except Exception:
            pass
        page.update()
        refresh_file_manager()

    search_mode_btn = ft.IconButton(
        icon=ft.Icons.SEARCH,
        tooltip="Search",
        on_click=show_search_view,
        icon_color=ACTIVE_TOOLBAR_ICON_COLOR,
    )
    files_mode_btn = ft.IconButton(
        icon=ft.Icons.FOLDER_OPEN,
        tooltip="My documents",
        on_click=show_files_view,
        icon_color=INACTIVE_TOOLBAR_ICON_COLOR,
    )

    upload_toolbar_btn = ft.IconButton(
        icon=ft.Icons.UPLOAD_FILE,
        tooltip="Add documents…",
        on_click=open_upload_dialog,
    )
    update_toolbar_btn = ft.IconButton(
        icon=ft.Icons.REFRESH,
        tooltip="Update index",
        on_click=_update_click,
    )
    clear_toolbar_btn = ft.IconButton(
        icon=ft.Icons.DELETE_OUTLINE,
        tooltip="Clear RAG index",
        on_click=_clear_click,
    )

    rag_toolbar = ft.Container(
        content=ft.Row(
            [
                upload_toolbar_btn,
                update_toolbar_btn,
                clear_toolbar_btn,
                ft.Container(expand=True),
                files_mode_btn,
                search_mode_btn,
            ],
            spacing=4,
        ),
        bgcolor=ft.Colors.GREY_900,
        padding=8,
    )

    # Dev: RAG context preview
    rag_preview_query = ft.TextField(
        hint_text="Query (e.g. user message)...",
        expand=True,
        height=36,
        text_style=ft.TextStyle(size=12),
        dense=True,
    )
    rag_preview_path = ft.TextField(
        hint_text="File path (for By path mode)...",
        expand=True,
        height=36,
        text_style=ft.TextStyle(size=12),
        dense=True,
        visible=False,
    )
    rag_preview_by_path = ft.Checkbox(
        label="By path (read_file)",
        value=False,
        on_change=lambda e: _toggle_rag_preview_mode(e, rag_preview_query, rag_preview_path),
    )

    def _parse_int_field(value: Any, default: int, min_val: int, max_val: int) -> int:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        try:
            return max(min_val, min(max_val, int(value)))
        except (TypeError, ValueError):
            return default

    rag_preview_top_k = ft.TextField(
        hint_text="top_k (1–50)",
        width=80,
        height=36,
        text_style=ft.TextStyle(size=11),
        dense=True,
    )
    rag_preview_max_chars = ft.TextField(
        hint_text="max_chars",
        width=80,
        height=36,
        text_style=ft.TextStyle(size=11),
        dense=True,
    )
    rag_preview_snippet_max = ft.TextField(
        hint_text="snippet_max",
        width=80,
        height=36,
        text_style=ft.TextStyle(size=11),
        dense=True,
    )

    def _toggle_rag_preview_mode(
        _e: ft.ControlEvent,
        query_tf: ft.TextField,
        path_tf: ft.TextField,
    ) -> None:
        by_path = rag_preview_by_path.value
        query_tf.visible = not by_path
        path_tf.visible = by_path
        try:
            query_tf.update()
            path_tf.update()
        except Exception:
            pass

    rag_preview_output = ft.TextField(
        read_only=True,
        multiline=True,
        min_lines=4,
        max_lines=12,
        expand=True,
        text_style=ft.TextStyle(size=11, font_family="monospace"),
        hint_text="RAG context will appear here after Preview.",
    )

    def _on_rag_preview_click(_e: ft.ControlEvent) -> None:
        by_path = rag_preview_by_path.value
        path_str = (rag_preview_path.value or "").strip()
        query = (rag_preview_query.value or "").strip()
        if by_path:
            if not path_str:
                rag_preview_output.value = "(Enter a file path and click Preview.)"
                rag_preview_output.update()
                return
        else:
            if not query:
                rag_preview_output.value = "(Enter a query and click Preview.)"
                rag_preview_output.update()
                return

        rag_preview_output.value = "Loading..."
        rag_preview_output.update()

        top_k = _parse_int_field(rag_preview_top_k.value, 10, 1, 50)
        max_chars_str = (rag_preview_max_chars.value or "").strip()
        snippet_max_str = (rag_preview_snippet_max.value or "").strip()
        max_chars = _parse_int_field(max_chars_str, 0, 1, 5000) if max_chars_str else None
        snippet_max = _parse_int_field(snippet_max_str, 0, 1, 5000) if snippet_max_str else None

        async def _fetch() -> None:
            try:
                if by_path:
                    ctx = await asyncio.to_thread(
                        get_rag_context_by_path,
                        path_str,
                        WORKFLOW_DESIGNER_ROLE_ID,
                        max_chars or None,
                        snippet_max or None,
                    )
                else:
                    ctx = await asyncio.to_thread(
                        get_rag_context,
                        query,
                        WORKFLOW_DESIGNER_ROLE_ID,
                        top_k,
                        max_chars,
                        snippet_max,
                    )
                rag_preview_output.value = ctx if ctx else "(No RAG context returned.)"
            except Exception as ex:
                rag_preview_output.value = f"Error: {ex}"
            try:
                rag_preview_output.update()
            except Exception:
                pass

        page.run_task(_fetch)

    rag_preview_btn = ft.OutlinedButton("Preview", on_click=_on_rag_preview_click)
    dev_rag_section = ft.Container(
        content=ft.Column(
            [
                ft.Text("Dev: RAG context preview", size=11, color=ft.Colors.GREY_500),
                ft.Row([rag_preview_by_path], spacing=8),
                ft.Row([rag_preview_query, rag_preview_path], spacing=8),
                ft.Row(
                    [
                        rag_preview_top_k,
                        rag_preview_max_chars,
                        rag_preview_snippet_max,
                        rag_preview_btn,
                    ],
                    spacing=8,
                ),
                ft.Text(
                    "Optional: top_k (search), max_chars, snippet_max. Leave blank for defaults.",
                    size=10,
                    color=ft.Colors.GREY_600,
                ),
                ft.Container(content=rag_preview_output, height=160),
            ],
            spacing=6,
            tight=True,
        ),
        padding=ft.Padding.symmetric(horizontal=0, vertical=12),
        border=ft.border.all(1, ft.Colors.GREY_700),
        border_radius=6,
        visible=show_rag_preview,
    )

    return ft.Column(
        [
            rag_toolbar,
            rag_main_view,
            dev_rag_section,
        ],
        expand=True,
        spacing=0,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
