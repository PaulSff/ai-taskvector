"""
RAG tab: mydata browser (folders + files), summary and pie chart.

Refresh runs ``rag/workflows/mydata_file_manager_refresh.json`` (MydataOrganize → MydataStorageReport)
and renders the returned payload.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import flet as ft

from gui.components.settings import get_mydata_dir, get_mydata_file_manager_refresh_workflow_path
from runtime.run import run_workflow

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


def build_rag_file_manager_panel() -> tuple[ft.Container, Callable[[], None]]:
    """
    Build a file-manager style view (breadcrumb + folder listing + summary + pie chart).

    ``refresh()`` runs the mydata file-manager refresh workflow and updates the UI from its outputs.
    """
    nav_parts: list[str] = []

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

    def refresh_file_manager() -> None:
        root = get_mydata_dir()
        try:
            out = run_workflow(
                get_mydata_file_manager_refresh_workflow_path(),
                initial_inputs={
                    "mydata_storage_report": {
                        "rel_parts": list(nav_parts),
                    }
                },
                format="dict",
                execution_timeout_s=60.0,
            )
        except Exception as ex:
            browser_rows.controls = [
                ft.Text(f"Workflow error: {ex}", size=12, color=ft.Colors.ERROR),
            ]
            summary_text.value = ""
            pie_image.visible = False
            pie_placeholder.visible = True
            for c in (breadcrumb_row, browser_rows, summary_text, pie_image, pie_placeholder):
                try:
                    c.update()
                except Exception:
                    pass
            return

        org = out.get("mydata_organize") or {}
        org_err = (org.get("error") or "").strip() if isinstance(org, dict) else ""

        rep = out.get("mydata_storage_report") or {}
        rep_err = (rep.get("error") or "").strip() if isinstance(rep, dict) else ""
        data = rep.get("data") if isinstance(rep, dict) else None
        if not isinstance(data, dict):
            data = {}

        rel_eff = data.get("rel_parts_effective")
        if isinstance(rel_eff, list):
            set_nav([str(x) for x in rel_eff if str(x).strip()])

        # Breadcrumb
        crumb_controls: list[ft.Control] = []
        acc: list[str] = []

        def _crumb_handler(parts: list[str]) -> Callable[[ft.ControlEvent], None]:
            def _h(_e: ft.ControlEvent) -> None:
                set_nav(parts)
                refresh_file_manager()

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
                        refresh_file_manager()

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
                            refresh_file_manager()

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
        else:
            pie_image.visible = False
            pie_placeholder.visible = True

        for c in (breadcrumb_row, browser_rows, summary_text, pie_image, pie_placeholder):
            try:
                c.update()
            except Exception:
                pass

    content = ft.Container(
        content=ft.Column(
            [
                ft.Text("My documents", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_300),
                ft.Text(
                    "Browse mydata (paths in .noindex.txt are hidden, same as RAG). "
                    "Refresh runs workflow: MydataOrganize → MydataStorageReport.",
                    size=11,
                    color=ft.Colors.GREY_500,
                ),
                ft.Container(height=6),
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
    return content, refresh_file_manager
