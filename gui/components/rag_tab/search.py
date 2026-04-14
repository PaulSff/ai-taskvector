"""
RAG tab: knowledge-base search panel (query + results via get_rag_search_formatted_and_rows).
"""
from __future__ import annotations

import asyncio
from typing import Any

import flet as ft

from assistants.roles import WORKFLOW_DESIGNER_ROLE_ID
from gui.chat.context.rag_context import get_rag_search_formatted_and_rows
from gui.utils.notifications import show_toast

from .download_helpers import download_path_or_url_to_disk


def _row_path_for_actions(row: dict[str, Any]) -> str:
    """Best path or URL to copy / send to chat (matches index metadata)."""
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    for key in ("file_path", "raw_json_path", "url"):
        v = str(meta.get(key) or "").strip()
        if v:
            return v
    return str(meta.get("source") or "").strip()


def build_rag_search_panel(
    page: ft.Page,
    *,
    chat_panel_api: dict[str, Any] | None = None,
) -> ft.Container:
    """Build the default Search view: query field, run button, scrollable results with copy / download / share."""
    results_column = ft.Column(
        [],
        spacing=4,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    search_query_tf = ft.TextField(
        hint_text="Search the knowledge base…",
        expand=True,
        dense=True,
        text_style=ft.TextStyle(size=13),
    )

    def _rebuild_result_rows(rows: list[dict[str, Any]], formatted_fallback: str) -> None:
        results_column.controls.clear()
        for row in rows:
            if not isinstance(row, dict):
                continue
            path_str = _row_path_for_actions(row)
            meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            ct = str(meta.get("content_type") or "").strip() or "hit"
            snippet = (row.get("text") or "").replace("\n", " ").strip()
            if len(snippet) > 220:
                snippet = snippet[:217] + "…"
            score = row.get("score")
            score_bit = ""
            if score is not None and isinstance(score, (int, float)):
                score_bit = f" · score {float(score):.3f}"

            async def _copy_path(_e: ft.ControlEvent, p: str = path_str) -> None:
                if not p:
                    return
                try:
                    await page.clipboard.set(p)
                except Exception:
                    return
                await show_toast(page, "Path copied")

            def _send_path_to_chat(_e: ft.ControlEvent, p: str = path_str) -> None:
                if not p:
                    return
                api = chat_panel_api or {}
                fn = api.get("add_file_path_reference")
                if callable(fn):
                    fn(p)
                    return

                async def _warn() -> None:
                    await show_toast(page, "Chat is not ready yet")

                page.run_task(_warn)

            async def _download_file(_e: ft.ControlEvent, p: str = path_str) -> None:
                await download_path_or_url_to_disk(page, p)

            subtitle = path_str if path_str else "(no path in metadata)"
            trailing = None
            if path_str:
                trailing = ft.Row(
                    [
                        ft.IconButton(
                            icon=ft.Icons.CONTENT_COPY,
                            icon_size=16,
                            icon_color=ft.Colors.GREY_400,
                            tooltip="Copy path",
                            style=ft.ButtonStyle(padding=2),
                            on_click=_copy_path,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DOWNLOAD,
                            icon_size=16,
                            icon_color=ft.Colors.GREY_400,
                            tooltip="Download file",
                            style=ft.ButtonStyle(padding=2),
                            on_click=_download_file,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CHAT_BUBBLE_OUTLINE,
                            icon_size=16,
                            icon_color=ft.Colors.GREY_400,
                            tooltip="Add path to chat context",
                            style=ft.ButtonStyle(padding=2),
                            on_click=_send_path_to_chat,
                        ),
                    ],
                    spacing=0,
                    tight=True,
                )

            results_column.controls.append(
                ft.ListTile(
                    dense=True,
                    title=ft.Text(snippet or "(empty chunk)", size=12, max_lines=3),
                    subtitle=ft.Text(
                        f"[{ct}] {subtitle}{score_bit}",
                        size=10,
                        color=ft.Colors.GREY_500,
                        font_family="monospace",
                        max_lines=2,
                    ),
                    trailing=trailing,
                )
            )

        if not results_column.controls:
            if (formatted_fallback or "").strip():
                results_column.controls.append(
                    ft.Container(
                        content=ft.Text(
                            formatted_fallback,
                            size=11,
                            font_family="monospace",
                            selectable=True,
                        ),
                        padding=ft.padding.only(top=4),
                    )
                )
            else:
                results_column.controls.append(
                    ft.Text("(No results.)", size=12, color=ft.Colors.GREY_500),
                )

    async def _run_main_search_async() -> None:
        query = (search_query_tf.value or "").strip()
        if not query:
            results_column.controls = [
                ft.Text("Enter a search query.", size=12, color=ft.Colors.GREY_500),
            ]
            results_column.update()
            return
        results_column.controls = [
            ft.Row(
                [
                    ft.ProgressRing(width=18, height=18, stroke_width=2),
                    ft.Text("Searching…", size=12, color=ft.Colors.GREY_400),
                ],
                spacing=8,
            ),
        ]
        results_column.update()
        try:
            formatted, rows = await asyncio.to_thread(
                get_rag_search_formatted_and_rows,
                query,
                WORKFLOW_DESIGNER_ROLE_ID,
                None,
                None,
                None,
            )
            _rebuild_result_rows(rows, formatted)
        except Exception as ex:
            results_column.controls = [
                ft.Text(f"Error: {ex}", size=12, color=ft.Colors.ERROR),
            ]
        try:
            results_column.update()
        except Exception:
            pass

    def _main_search_click(_e: ft.ControlEvent) -> None:
        page.run_task(_run_main_search_async)

    search_query_tf.on_submit = lambda _e: page.run_task(_run_main_search_async)

    search_go_btn = ft.IconButton(
        icon=ft.Icons.SEARCH,
        tooltip="Search",
        on_click=_main_search_click,
    )

    return ft.Container(
        content=ft.Column(
            [
                ft.Text("Search", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_300),
                ft.Text(
                    "Query the knowledge base.",
                    size=11,
                    color=ft.Colors.GREY_500,
                ),
                ft.Container(height=8),
                ft.Row(
                    [search_query_tf, search_go_btn],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text("Results", size=12, weight=ft.FontWeight.W_500, color=ft.Colors.GREY_400),
                ft.Container(content=results_column, expand=True),
            ],
            expand=True,
            spacing=6,
        ),
        padding=24,
        expand=True,
    )
