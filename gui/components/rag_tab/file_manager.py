"""
RAG tab: mydata browser (folders + files), summary and pie chart.

Refresh uses ``rag/mydata_file_manager_ops`` on a worker thread (no workflow) for lower latency.
Phase 1 returns the current folder listing immediately. Phase 2 (full-tree scan + matplotlib pie)
runs only when the storage chart cache is missing, the mydata root path changed, or the caller asks
for ``refresh_storage_chart=True`` (upload). Folder navigation reuses the cached summary and pie.
Root auto-organize runs only when ``organize=True`` (tab open, upload, index), not when navigating.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Coroutine

import flet as ft

from gui.components.settings import get_mydata_dir
from rag.mydata_file_manager_ops import (
    build_mydata_listing_view_model,
    build_mydata_storage_report,
    has_mydata_root_organizable_files,
    organize_mydata_root,
)

# 1×1 transparent PNG — ``ft.Image`` requires ``src`` at construction time (Flet 0.82+).
_PIE_PLACEHOLDER_SRC = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _human_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit, div in (("KB", 1024), ("MB", 1024**2), ("GB", 1024**3)):
        if n < div * 1024:
            return f"{n / div:.1f} {unit}"
    return f"{n / 1024**3:.1f} TB"


def _file_row_icon(suffix: str) -> str:
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


def build_rag_file_manager_panel(
    page: ft.Page,
) -> tuple[ft.Container, Callable[..., None], Callable[..., Coroutine[Any, Any, None]]]:
    """
    Build a file-manager style view (breadcrumb + folder listing + summary + pie chart).

    ``refresh_file_manager(organize=True, refresh_storage_chart=False)`` — default rebuilds the pie
    only when there is no cache yet or mydata dir changed; pass ``refresh_storage_chart=True`` after
    upload. ``refresh_file_manager(organize=False)`` is used for folder navigation (listing only;
    cached chart). ``await refresh_file_manager_async(...)`` when the caller must wait (e.g. after
    RAG index update).
    """
    nav_parts: list[str] = []
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

    def set_nav(parts: list[str]) -> None:
        nav_parts[:] = list(parts)

    browser_rows = ft.Column([], spacing=2, scroll=ft.ScrollMode.AUTO, expand=True)
    breadcrumb_row = ft.Row([], wrap=True, spacing=0)
    summary_text = ft.Text("", size=12, color=ft.Colors.GREY_400, selectable=True)
    pie_image = ft.Image(
        src=_PIE_PLACEHOLDER_SRC,
        visible=False,
        width=300,
        height=240,
        fit=ft.BoxFit.CONTAIN,
    )
    pie_placeholder = ft.Text("Add files to see a storage breakdown.", size=11, color=ft.Colors.GREY_600)
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

    def _run_phase2() -> dict[str, Any]:
        return build_mydata_storage_report(get_mydata_dir())

    def _apply_refresh_fatal_error(ex: Exception) -> None:
        browser_rows.controls = [
            ft.Text(f"Could not load mydata: {ex}", size=12, color=ft.Colors.ERROR),
        ]
        summary_text.value = ""
        pie_image.visible = False
        pie_placeholder.visible = True
        pie_placeholder.value = "Add files to see a storage breakdown."

    def _start_refresh() -> int:
        _refresh_gen[0] += 1
        return _refresh_gen[0]

    def _apply_file_manager_payload(
        data: dict[str, Any],
        *,
        org_err: str = "",
        rep_err: str = "",
        chart_pending: bool = False,
    ) -> None:
        root = get_mydata_dir()

        rel_eff = data.get("rel_parts_effective")
        if isinstance(rel_eff, list):
            set_nav([str(x) for x in rel_eff if str(x).strip()])

        crumb_controls: list[ft.Control] = []
        acc: list[str] = []

        def _crumb_handler(parts: list[str]) -> Callable[[ft.ControlEvent], None]:
            def _h(_e: ft.ControlEvent) -> None:
                set_nav(parts)
                _schedule_do_refresh()

            return _h

        crumb_controls.append(
            ft.TextButton(
                "mydata",
                style=ft.ButtonStyle(padding=ft.padding.symmetric(horizontal=6, vertical=2)),
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
                    style=ft.ButtonStyle(padding=ft.padding.symmetric(horizontal=6, vertical=2)),
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
            rows.append(ft.Text("The mydata folder does not exist yet.", size=12, color=ft.Colors.GREY_500))
        else:
            if nav_parts:

                def _go_up(_e: ft.ControlEvent) -> None:
                    if nav_parts:
                        nav_parts.pop()
                        _schedule_do_refresh()

                rows.append(
                    ft.ListTile(
                        leading=ft.Icon(ft.Icons.ARROW_UPWARD, size=20, color=ft.Colors.GREY_400),
                        title=ft.Text("Up one level", size=13),
                        dense=True,
                        on_click=_go_up,
                    )
                )

            entries_raw = data.get("entries")
            entries: list[dict[str, Any]] = entries_raw if isinstance(entries_raw, list) else []

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

                    def _open_dir(path: Path) -> Callable[[ft.ControlEvent], None]:
                        def _h(_e: ft.ControlEvent) -> None:
                            try:
                                rel = path.resolve().relative_to(root.resolve())
                                set_nav(list(rel.parts))
                            except ValueError:
                                set_nav([path.name])
                            _schedule_do_refresh()

                        return _h

                    rows.append(
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.FOLDER, color=ft.Colors.AMBER_200),
                            title=ft.Text(name, size=13, font_family="monospace"),
                            subtitle=ft.Text("Folder", size=10, color=ft.Colors.GREY_500),
                            dense=True,
                            on_click=_open_dir(path_obj),
                        )
                    )
                else:
                    suf = Path(name).suffix
                    rows.append(
                        ft.ListTile(
                            leading=ft.Icon(_file_row_icon(suf), color=ft.Colors.GREY_300),
                            title=ft.Text(name, size=13, font_family="monospace"),
                            subtitle=ft.Text(
                                f"{_human_bytes(sz or 0)} · {rel_str}",
                                size=10,
                                color=ft.Colors.GREY_500,
                            ),
                            dense=True,
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

        summary_text.value = str(data.get("summary_text") or "")
        pie_src = data.get("pie_src")
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

        for c in (loading_row, breadcrumb_row, browser_rows, summary_text, pie_image, pie_placeholder):
            try:
                c.update()
            except Exception:
                pass
        try:
            page.update()
        except Exception:
            pass

    async def _do_refresh(
        gen: int,
        *,
        organize: bool = False,
        refresh_storage_chart: bool = False,
    ) -> None:
        nonlocal _storage_chart_cache, _storage_chart_cache_root
        loading_row.visible = True
        try:
            loading_row.update()
        except Exception:
            pass
        try:
            page.update()
        except Exception:
            pass

        org_err = ""
        listing: dict[str, Any] = {}
        try:
            org_err, listing = await asyncio.to_thread(_run_phase1, organize)
        except Exception as ex:
            if gen == _refresh_gen[0]:
                _apply_refresh_fatal_error(ex)
            return
        finally:
            if gen == _refresh_gen[0]:
                loading_row.visible = False
            try:
                loading_row.update()
            except Exception:
                pass
            try:
                page.update()
            except Exception:
                pass

        if gen != _refresh_gen[0]:
            return

        root = get_mydata_dir()
        need_storage_scan = refresh_storage_chart or not _storage_cache_valid(root)

        if need_storage_scan:
            loading_partial = {
                **listing,
                "summary_text": "Calculating storage breakdown…",
                "pie_src": None,
            }
            _apply_file_manager_payload(loading_partial, org_err=org_err, rep_err="", chart_pending=True)

            try:
                report = await asyncio.to_thread(_run_phase2)
            except Exception as ex:
                if gen == _refresh_gen[0]:
                    fail = {
                        **listing,
                        "summary_text": f"Could not build storage summary ({ex}).",
                        "pie_src": None,
                    }
                    _apply_file_manager_payload(
                        fail,
                        org_err=org_err,
                        rep_err=str(ex)[:200],
                        chart_pending=False,
                    )
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

            merged = {**listing, **report}
            _apply_file_manager_payload(merged, org_err=org_err, rep_err="", chart_pending=False)
        else:
            cached = _storage_chart_cache or {}
            merged = {**listing, **cached}
            _apply_file_manager_payload(merged, org_err=org_err, rep_err="", chart_pending=False)

    def _schedule_do_refresh(_e: ft.ControlEvent | None = None, *, organize: bool = False) -> None:
        gen = _start_refresh()

        async def _run_refresh_task() -> None:
            await _do_refresh(gen, organize=organize, refresh_storage_chart=False)

        page.run_task(_run_refresh_task)

    def refresh_file_manager(
        organize: bool = True,
        *,
        refresh_storage_chart: bool = False,
    ) -> None:
        gen = _start_refresh()

        async def _run_refresh_task() -> None:
            await _do_refresh(
                gen,
                organize=organize,
                refresh_storage_chart=refresh_storage_chart,
            )

        page.run_task(_run_refresh_task)

    async def refresh_file_manager_async(
        organize: bool = True,
        *,
        refresh_storage_chart: bool = False,
    ) -> None:
        await _do_refresh(
            _start_refresh(),
            organize=organize,
            refresh_storage_chart=refresh_storage_chart,
        )

    content = ft.Container(
        content=ft.Column(
            [
                ft.Text("My documents", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_300),
                ft.Text(
                    "The paths defined in .noindex.txt are hidden.",
                    size=11,
                    color=ft.Colors.GREY_500,
                ),
                ft.Container(height=6),
                loading_row,
                ft.Container(
                    content=breadcrumb_row,
                    padding=ft.padding.only(bottom=4),
                ),
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text("Folder", size=11, weight=ft.FontWeight.W_500, color=ft.Colors.GREY_400),
                                    ft.Container(
                                        content=browser_rows,
                                        expand=True,
                                        border=ft.border.all(1, ft.Colors.GREY_800),
                                        border_radius=6,
                                        padding=8,
                                    ),
                                ],
                                expand=True,
                                spacing=4,
                            ),
                            expand=3,
                        ),
                        ft.Container(width=12),
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text("Storage by type", size=11, weight=ft.FontWeight.W_500, color=ft.Colors.GREY_400),
                                    ft.Container(
                                        content=ft.Column(
                                            [
                                                pie_image,
                                                pie_placeholder,
                                            ],
                                            tight=True,
                                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                        ),
                                        alignment=ft.Alignment(0, 0),
                                    ),
                                    ft.Text("Summary", size=11, weight=ft.FontWeight.W_500, color=ft.Colors.GREY_400),
                                    ft.Container(content=summary_text, padding=ft.padding.only(top=4)),
                                ],
                                spacing=8,
                                scroll=ft.ScrollMode.AUTO,
                                expand=True,
                            ),
                            expand=2,
                        ),
                    ],
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ],
            expand=True,
            spacing=4,
        ),
        padding=24,
        expand=True,
    )
    return content, refresh_file_manager, refresh_file_manager_async
