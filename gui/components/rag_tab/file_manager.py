from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, cast

import flet as ft
from flet import Event, IconButton, ListTile, TextButton

from gui.components.rag_tab.dialog_preview_markdown import open_markdown_dialog
from gui.components.settings import get_mydata_dir
from gui.utils.notifications import show_toast
from rag.mydata_file_manager_ops import (
    build_mydata_listing_view_model,
    has_mydata_root_organizable_files,
    organize_mydata_root,
)

from .download_helpers import download_path_or_url_to_disk


def build_rag_file_browser_panel(
    page: ft.Page,
    *,
    chat_panel_api: dict[str, Any] | None = None,
) -> tuple[ft.Container, Callable[..., None], Callable[..., Coroutine[Any, Any, None]]]:
    nav_parts: list[str] = []
    _refresh_gen: list[int] = [0]

    def set_nav(parts: list[str]) -> None:
        nav_parts[:] = list(parts)

    browser_rows = ft.Column([], spacing=2, scroll=ft.ScrollMode.AUTO, expand=True)
    breadcrumb_row = ft.Row([], wrap=True, spacing=0)

    loading_row = ft.Row(
        [
            ft.ProgressRing(width=20, height=20),
            ft.Text("Loading mydata…", size=12, color=ft.Colors.GREY_400),
        ],
        spacing=8,
        visible=False,
    )

    def _run_phase1(organize: bool) -> tuple[str, dict[str, Any]]:
        root = get_mydata_dir()
        org_err = ""
        if organize and has_mydata_root_organizable_files(root):
            try:
                organize_mydata_root(root)
            except OSError as e:
                org_err = str(e)[:300]
        listing = build_mydata_listing_view_model(root, list(nav_parts))
        return org_err, listing

    def _apply_refresh_fatal_error(ex: Exception) -> None:
        browser_rows.controls = [
            ft.Text(f"Could not load mydata: {ex}", size=12, color=ft.Colors.ERROR),
        ]
        try:
            page.update()
        except RuntimeError:
            pass

    def _start_refresh() -> int:
        _refresh_gen[0] += 1
        return _refresh_gen[0]

    def _human_bytes(n: int) -> str:
        if n < 1024:
            return f"{n} B"
        for unit, div in (("KB", 1024), ("MB", 1024**2), ("GB", 1024**3)):
            if n < div * 1024:
                return f"{n / div:.1f} {unit}"
        return f"{n / 1024**3:.1f} TB"

    def _file_row_icon(suffix: str) -> ft.IconData:
        s = suffix.lower()
        if s == ".pdf":
            return ft.Icons.PICTURE_AS_PDF
        if s in {".doc", ".docx"}:
            return ft.Icons.DESCRIPTION
        if s in {".xlsx", ".xls", ".csv", ".tsv"}:
            return ft.Icons.TABLE_CHART
        if s in {".pptx", ".ppt"}:
            return ft.Icons.SLIDESHOW
        if s == ".html":
            return ft.Icons.HTML
        if s == ".md":
            return ft.Icons.ARTICLE
        if s == ".json":
            return ft.Icons.DATA_OBJECT
        return ft.Icons.INSERT_DRIVE_FILE

    def _apply_file_browser_payload(
        data: dict[str, Any],
        *,
        org_err: str = "",
        rep_err: str = "",
    ) -> None:
        root = get_mydata_dir()

        rel_eff = data.get("rel_parts_effective")
        if isinstance(rel_eff, list):
            set_nav([str(x) for x in rel_eff if str(x).strip()])

        crumb_controls: list[ft.Control] = []
        acc: list[str] = []

        def _crumb_handler(parts: list[str]) -> Callable[[Event[TextButton]], None]:
            def _h(e: Event[TextButton]) -> None:
                set_nav(parts)
                _schedule_do_refresh()

            return _h

        crumb_controls.append(
            TextButton(
                "mydata",
                style=ft.ButtonStyle(
                    padding=ft.padding.Padding.symmetric(horizontal=6, vertical=2)
                ),
                on_click=_crumb_handler([]),
            )
        )

        for part in nav_parts:
            crumb_controls.append(ft.Text("/", size=12, color=ft.Colors.GREY_600))
            acc.append(part)
            seg = list(acc)
            crumb_controls.append(
                ft.TextButton(
                    part,
                    style=ft.ButtonStyle(
                        padding=ft.padding.Padding.symmetric(horizontal=6, vertical=2)
                    ),
                    on_click=_crumb_handler(seg),
                )
            )

        breadcrumb_row.controls = crumb_controls

        rows: list[ft.Control] = []
        if org_err:
            rows.append(ft.Text(f"Organize: {org_err}", size=11, color=ft.Colors.AMBER_200))
        if rep_err:
            rows.append(ft.Text(f"Report: {rep_err}", size=11, color=ft.Colors.ERROR))
        for msg in data.get("list_errors") or []:
            if isinstance(msg, str) and msg.strip():
                rows.append(ft.Text(msg[:200], size=11, color=ft.Colors.ERROR))

        if not root.exists():
            rows.append(
                ft.Text(
                    "The mydata folder does not exist yet.",
                    size=12,
                    color=ft.Colors.GREY_500,
                )
            )
        else:
            if nav_parts:

                def _go_up(e: Event[ListTile]) -> None:
                    if nav_parts:
                        nav_parts.pop()
                        _schedule_do_refresh()

                rows.append(
                    ft.ListTile(
                        leading=ft.Icon(
                            ft.Icons.ARROW_UPWARD, size=20, color=ft.Colors.GREY_400
                        ),
                        title=ft.Text("Up one level", size=13),
                        dense=True,
                        on_click=_go_up,
                    )
                )

            entries_raw = data.get("entries")
            entries: list[dict[str, Any]] = (
                entries_raw if isinstance(entries_raw, list) else []
            )

            listed = 0
            for ent in entries:
                if not isinstance(ent, dict):
                    continue
                name = str(ent.get("name") or "")
                if not name or name.startswith("."):
                    continue
                listed += 1
                is_dir = bool(ent.get("is_dir"))
                sz_raw = ent.get("size")
                sz = int(sz_raw) if isinstance(sz_raw, int) else None
                rel_str = str(ent.get("rel") or name)

                if is_dir:
                    path_obj = root / rel_str if rel_str else root / name

                    def _open_dir(path: Path) -> Callable[[Event[ListTile]], None]:
                        def _h(e: Event[ListTile]) -> None:
                            try:
                                rel = path.resolve().relative_to(root.resolve())
                                set_nav(list(rel.parts))
                            except ValueError:
                                set_nav([path.name])
                            _schedule_do_refresh()

                        return _h

                    rows.append(
                        ft.ListTile(
                            leading=ft.Icon(
                                ft.Icons.FOLDER, color=ft.Colors.AMBER_200
                            ),
                            title=ft.Text(name, size=13, font_family="monospace"),
                            subtitle=ft.Text(
                                "Folder", size=10, color=ft.Colors.GREY_500
                            ),
                            dense=True,
                            on_click=_open_dir(path_obj),
                        )
                    )
                else:
                    suf = Path(name).suffix
                    try:
                        abs_path_str = str((root / rel_str).resolve())
                    except OSError:
                        abs_path_str = str(root / rel_str)

                    def _copy_file_path(e: Event[IconButton], p: str = abs_path_str) -> None:
                        async def _do() -> None:
                            try:
                                await page.clipboard.set(p)
                            except (OSError, ValueError):
                                return
                            await show_toast(page, "Path copied")
                        page.run_task(_do)

                    def _send_path_to_chat(e: ft.Event[ft.IconButton], p: str = abs_path_str) -> None:
                        api = chat_panel_api or {}
                        fn = api.get("add_file_path_reference")
                        if callable(fn):
                            try:
                                result = fn(p)
                            except (TypeError, ValueError):
                                result = False

                            if asyncio.iscoroutine(result):
                                page.run_task(lambda: result)

                            if result is False:

                                async def _warn() -> None:
                                    await show_toast(page, "Chat is not ready yet")

                                page.run_task(_warn)
                            return

                        async def _warn() -> None:
                            await show_toast(page, "Chat is not ready yet")

                        page.run_task(_warn)

                    def _download_file(e: ft.Event[ft.IconButton], p: str = abs_path_str) -> None:
                        async def coro() -> None:
                            await download_path_or_url_to_disk(page, p)
                        page.run_task(coro)

                    tile_click_last_ts = [0.0]
                    double_click_window_s = 0.35

                    async def _preview_markdown_async(p: str = abs_path_str, n: str = name) -> None:
                        open_markdown_dialog(
                            page,
                            local_path=p,
                            title=f"Preview: {n}",
                        )

                    def _on_tile_double_click(
                        e: ft.Event[ft.ListTile],
                        last_ts: list[float] = tile_click_last_ts,
                        window_s: float = double_click_window_s,
                        preview_fn=_preview_markdown_async,
                    ) -> None:
                        now = time.monotonic()
                        if now - last_ts[0] <= window_s:
                            last_ts[0] = 0.0
                            page.run_task(preview_fn)
                        else:
                            last_ts[0] = now

                    rows.append(
                        ft.ListTile(
                            leading=ft.Icon(
                                _file_row_icon(suf), color=ft.Colors.GREY_300
                            ),
                            title=ft.Text(name, size=13, font_family="monospace"),
                            subtitle=ft.Text(
                                f"{_human_bytes(sz or 0)} · {rel_str}",
                                size=10,
                                color=ft.Colors.GREY_500,
                            ),
                            dense=True,
                            on_click=_on_tile_double_click,
                            trailing=ft.Row(
                                cast(
                                    list[ft.Control],
                                    [
                                        ft.IconButton(
                                            icon=ft.Icons.CONTENT_COPY,
                                            icon_size=16,
                                            icon_color=ft.Colors.GREY_400,
                                            tooltip="Copy full path",
                                            style=ft.ButtonStyle(padding=2),
                                            on_click=_copy_file_path,
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
                                ),
                                spacing=0,
                                tight=True,
                            ),
                        )
                    )

            if listed == 0 and not (org_err or rep_err):
                rows.append(
                    ft.Text(
                        "This folder is empty." if nav_parts else "No files yet. Upload from the toolbar.",
                        size=12,
                        color=ft.Colors.GREY_500,
                    )
                )

        browser_rows.controls = rows

        for c in (loading_row, breadcrumb_row, browser_rows):
            try:
                c.update()
            except RuntimeError:
                pass
        try:
            page.update()
        except RuntimeError:
            pass

    async def _do_refresh(
        gen: int,
        *,
        organize: bool = False,
    ) -> None:
        loading_row.visible = True
        try:
            loading_row.update()
        except RuntimeError:
            pass
        try:
            page.update()
        except RuntimeError:
            pass

        org_err = ""
        listing: dict[str, Any] = {}
        try:
            org_err, listing = await asyncio.to_thread(_run_phase1, organize)
        except OSError as ex:
            if gen == _refresh_gen[0]:
                _apply_refresh_fatal_error(ex)
            return
        finally:
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

        if gen != _refresh_gen[0]:
            return

        _apply_file_browser_payload(listing, org_err=org_err, rep_err="")

    def _schedule_do_refresh(
        _e: ft.ControlEvent | None = None, *, organize: bool = False
    ) -> None:
        gen = _start_refresh()

        async def _run_refresh_task() -> None:
            await _do_refresh(gen, organize=organize)

        page.run_task(_run_refresh_task)

    def refresh_file_browser(
        organize: bool = True,
        *,
        refresh_storage_chart: bool = False,  # ignored; keeps signature compatibility
    ) -> None:
        gen = _start_refresh()

        async def _run_refresh_task() -> None:
            await _do_refresh(gen, organize=organize)

        page.run_task(_run_refresh_task)

    async def refresh_file_browser_async(
        organize: bool = True,
        *,
        refresh_storage_chart: bool = False,  # ignored; keeps signature compatibility
    ) -> None:
        await _do_refresh(_start_refresh(), organize=organize)

    content = ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    "My documents",
                    size=14,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.GREY_300,
                ),
                ft.Text(
                    "The paths defined in .noindex.txt are hidden.",
                    size=11,
                    color=ft.Colors.GREY_500,
                ),
                ft.Container(height=6),
                loading_row,
                ft.Container(
                    content=breadcrumb_row,
                    padding=ft.padding.Padding.only(bottom=4),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "Folder",
                                size=11,
                                weight=ft.FontWeight.W_500,
                                color=ft.Colors.GREY_400,
                            ),
                            ft.Container(
                                content=browser_rows,
                                expand=True,
                                border=ft.border.Border.all(1, ft.Colors.GREY_800),
                                border_radius=6,
                                padding=8,
                            ),
                        ],
                        expand=True,
                        spacing=4,
                    ),
                    expand=True,
                ),
            ],
            expand=True,
            spacing=4,
        ),
        padding=24,
        expand=True,
    )

    return content, refresh_file_browser, refresh_file_browser_async
