"""
RAG tab: knowledge-base search panel (query + results via get_rag_context).
"""
from __future__ import annotations

import asyncio

import flet as ft

from assistants.roles import WORKFLOW_DESIGNER_ROLE_ID
from gui.chat.context.rag_context import get_rag_context


def build_rag_search_panel(page: ft.Page) -> ft.Container:
    """Build the default Search view: query field, run button, read-only results."""
    search_results_tf = ft.TextField(
        read_only=True,
        multiline=True,
        expand=True,
        min_lines=8,
        text_style=ft.TextStyle(size=11, font_family="monospace"),
        hint_text="Results appear here.",
    )

    search_query_tf = ft.TextField(
        hint_text="Search the knowledge base…",
        expand=True,
        dense=True,
        text_style=ft.TextStyle(size=13),
    )

    async def _run_main_search_async() -> None:
        query = (search_query_tf.value or "").strip()
        if not query:
            search_results_tf.value = "Enter a search query."
            search_results_tf.update()
            return
        search_results_tf.value = "Searching…"
        search_results_tf.update()
        try:
            ctx = await asyncio.to_thread(
                get_rag_context,
                query,
                WORKFLOW_DESIGNER_ROLE_ID,
                None,
                None,
                None,
            )
            search_results_tf.value = ctx if ctx else "(No results.)"
        except Exception as ex:
            search_results_tf.value = f"Error: {ex}"
        try:
            search_results_tf.update()
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
                    "Query workflows, units, and documents indexed for Workflow Designer and RL Coach.",
                    size=11,
                    color=ft.Colors.GREY_500,
                ),
                ft.Container(height=8),
                ft.Row(
                    [search_query_tf, search_go_btn],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(content=search_results_tf, expand=True),
            ],
            expand=True,
            spacing=6,
        ),
        padding=24,
        expand=True,
    )
