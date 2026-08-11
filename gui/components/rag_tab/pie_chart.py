from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import flet as ft

from gui.components.settings import get_mydata_dir
from rag.mydata_file_manager_ops import build_mydata_storage_report

_PIE_PLACEHOLDER_SRC = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def build_rag_storage_pie_panel(
    page: ft.Page,
) -> tuple[
    ft.Container,
    Callable[..., None],
    Callable[..., Coroutine[Any, Any, None]],
]:
    _refresh_gen: list[int] = [0]
    _storage_chart_cache: dict[str, Any] | None = None
    _storage_chart_cache_root: Path | None = None

    def _storage_cache_valid(root: Path) -> bool:
        if _storage_chart_cache is None or _storage_chart_cache_root is None:
            return False
        try:
            return root.resolve() == _storage_chart_cache_root
        except OSError:
            return False

    pie_image = ft.Image(
        src=_PIE_PLACEHOLDER_SRC,
        visible=False,
        width=300,
        height=240,
        fit=ft.BoxFit.CONTAIN,
    )
    pie_placeholder = ft.Text(
        "Add files to see a storage breakdown.", size=11, color=ft.Colors.GREY_600
    )

    summary_text = ft.Text("", size=12, color=ft.Colors.GREY_400, selectable=True)

    loading_row = ft.Row(
        [
            ft.ProgressRing(width=20, height=20),
            ft.Text("Loading mydata…", size=12, color=ft.Colors.GREY_400),
        ],
        spacing=8,
        visible=False,
    )

    def _apply_pie_payload(
        *,
        merged: dict[str, Any],
        rep_err: str = "",
        chart_pending: bool = False,
    ) -> None:
        pie_src = merged.get("pie_src")
        if isinstance(pie_src, str) and pie_src.startswith("data:image"):
            pie_image.src = pie_src
            pie_image.visible = True
            pie_placeholder.visible = False
            pie_placeholder.value = "Add files to see a storage breakdown."
        else:
            pie_image.visible = False
            pie_placeholder.visible = True
            if chart_pending:
                pie_placeholder.value = "Scanning mydata for the chart…"
            else:
                pie_placeholder.value = "Add files to see a storage breakdown."

        summary_text.value = str(merged.get("summary_text") or "")

        if rep_err:
            summary_text.value = f"{summary_text.value}\n({rep_err[:200]})"

        for c in (loading_row, pie_image, pie_placeholder, summary_text):
            try:
                c.update()
            except RuntimeError:
                pass
        try:
            page.update()
        except RuntimeError:
            pass

    def _apply_fatal_error(ex: Exception) -> None:
        pie_image.visible = False
        pie_placeholder.visible = True
        pie_placeholder.value = f"Could not load mydata chart: {ex}"
        summary_text.value = ""
        try:
            page.update()
        except RuntimeError:
            pass

    def _start_refresh() -> int:
        _refresh_gen[0] += 1
        return _refresh_gen[0]

    async def _do_refresh(
        gen: int,
        *,
        refresh_storage_chart: bool = False,
    ) -> None:
        nonlocal _storage_chart_cache, _storage_chart_cache_root

        loading_row.visible = True
        try:
            loading_row.update()
        except RuntimeError:
            pass
        try:
            page.update()
        except RuntimeError:
            pass

        root = get_mydata_dir()
        need_storage_scan = refresh_storage_chart or not _storage_cache_valid(root)

        if need_storage_scan:
            _apply_pie_payload(
                merged={"summary_text": "", "pie_src": None},
                rep_err="",
                chart_pending=True,
            )

            try:
                report = await asyncio.to_thread(build_mydata_storage_report, root)
            except (OSError, ValueError) as ex:
                if gen == _refresh_gen[0]:
                    _apply_fatal_error(ex)
                return

            if gen != _refresh_gen[0]:
                return

            _storage_chart_cache = {
                "summary_text": report.get("summary_text"),
                "pie_src": report.get("pie_src"),
            }
            try:
                _storage_chart_cache_root = root.resolve()
            except OSError:
                _storage_chart_cache_root = None

            _apply_pie_payload(merged=report, chart_pending=False)
        else:
            cached = _storage_chart_cache or {}
            _apply_pie_payload(merged=cached, chart_pending=False)

        if gen == _refresh_gen[0]:
            loading_row.visible = False
            try:
                loading_row.update()
            except RuntimeError:
                pass
            try:
                page.update()
            except RuntimeError:
                pass

    async def refresh_storage_pie(
        *,
        refresh_storage_chart: bool = False,
    ) -> None:
        await _do_refresh(_start_refresh(), refresh_storage_chart=refresh_storage_chart)

    # keep sync wrapper for callers that expect it
    def refresh_storage_pie_sync(
        *,
        refresh_storage_chart: bool = False,
    ) -> None:
        async def _run() -> None:
            await refresh_storage_pie(refresh_storage_chart=refresh_storage_chart)

        page.run_task(_run)

    content = ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    "Storage by type",
                    size=11,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.GREY_400,
                ),
                loading_row,
                ft.Container(
                    content=ft.Column(
                        [pie_image, pie_placeholder],
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    alignment=ft.Alignment(0, 0),
                ),
                ft.Text(
                    "Summary:",
                    size=11,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.GREY_400,
                ),
                ft.Container(
                    content=summary_text,
                    padding=ft.padding.Padding.only(top=4),
                ),
            ],
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        ),
        expand=True,
        padding=24,
    )

    # return types: sync callback, async callback
    return content, refresh_storage_pie_sync, refresh_storage_pie
