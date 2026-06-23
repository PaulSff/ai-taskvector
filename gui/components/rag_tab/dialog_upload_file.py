from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable, cast

import flet as ft

from gui.components.settings import get_mydata_dir
from gui.utils.file_picker import register_file_picker

from .helpers import (
    RAG_ADD_FOLDER_SUFFIXES,
    copy_rag_source_paths_to_mydata,
    organize_mydata_root_files,
    run_rag_index_update_async,
)


def build_rag_upload_file_dialog(
    page: ft.Page,
    *,
    toast: Callable[[str], None],
    on_mydata_changed: Callable[[], None],
) -> tuple[ft.AlertDialog, Callable[[ft.ControlEvent], None]]:
    """
    Build modal "Add documents" dialog and an opener callback.

    ``on_mydata_changed`` runs after a successful URL download or file copy (e.g. refresh file list).
    """
    status_txt = ft.Text("", size=12, color=ft.Colors.GREY_400)
    progress_row = ft.Row(
        [ft.ProgressRing(width=20, height=20), ft.Text("Working…", size=12)],
        visible=False,
        spacing=8,
    )
    url_tf = ft.TextField(
        label="URL",
        hint_text="e.g. https://example.com/workflow.json",
        expand=True,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )

    def _show_progress(show: bool) -> None:
        progress_row.visible = show
        progress_row.update()
        page.update()

    async def _download_url_to_mydata(url: str) -> None:
        status_txt.value = "Downloading..."
        _show_progress(True)
        try:
            import urllib.request

            req = urllib.request.Request(url, headers={"User-Agent": "Flet-RAG/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            name = Path(url.split("?")[0]).name or "downloaded"
            if not name or name == ".":
                name = "downloaded"
            mydata = get_mydata_dir()
            mydata.mkdir(parents=True, exist_ok=True)
            dest = mydata / name
            counter = 0
            stem, suffix = dest.stem, dest.suffix
            while dest.exists():
                counter += 1
                dest = mydata / f"{stem}_{counter}{suffix}"
            dest.write_bytes(data)
            await asyncio.to_thread(organize_mydata_root_files)
            status_txt.value = "Downloaded to mydata. Use Update (index) to index."
            toast("Downloaded. Click Update (index) to index.")
            on_mydata_changed()
        except Exception as e:
            status_txt.value = str(e)[:200]
            toast(f"Error: {e}")
        _show_progress(False)
        status_txt.update()
        page.update()

    def _add_from_url() -> None:
        raw = (url_tf.value or "").strip()
        if not raw:
            toast("Enter a URL.")
            return
        if not raw.startswith(("http://", "https://")):
            toast("URL must start with http:// or https://")
            return

        async def _url_task() -> None:
            await _download_url_to_mydata(raw)

        page.run_task(_url_task)

    file_picker = register_file_picker(page)

    copied_count = {"n": 0}  # mutable holder for last copy result

    async def _start_index_update() -> None:
        status_txt.value = f"Index requested. copied_count={copied_count['n']}"
        status_txt.update()
        page.update()

        if copied_count["n"] <= 0:
            toast("Pick files first (or download from URL).")
            return

        await run_rag_index_update_async(
            page,
            toast,
            dialog_status=status_txt,
            dialog_progress_row=progress_row,
        )
        on_mydata_changed()
        copied_count["n"] = 0

        upload_dlg.open = False  # <-- close dialog
        page.update()

    def _pick_files_click() -> None:
        if file_picker:
            page.run_task(_pick_files_and_copy)

    async def _pick_files_and_copy() -> None:
        copied_count["n"] = 0  # reset each time you pick

        if not file_picker:
            toast("File picker not available. Use folder path or URL.")
            return

        try:
            files = await file_picker.pick_files(allow_multiple=True)
        except Exception as e:
            toast(f"File picker error: {e}")
            return

        if not files:
            status_txt.value = "No files selected."
            status_txt.update()
            page.update()
            return

        paths: list[Path] = []
        for f in files:
            path = getattr(f, "path", None)
            if not path and getattr(f, "name", None):
                toast(
                    "Selected files are not available as paths (e.g. in browser). Use folder path or URL."
                )
                return
            if path and Path(path).is_file():
                p = Path(path)
                if p.suffix.lower() in RAG_ADD_FOLDER_SUFFIXES:
                    paths.append(p)

        if not paths:
            toast("No supported files selected (e.g. .pdf, .md, .json).")
            status_txt.value = "No supported files selected."
            status_txt.update()
            page.update()
            return

        status_txt.value = f"Copying {len(paths)} file(s) to mydata..."
        _show_progress(True)
        status_txt.update()
        page.update()

        try:
            n = await asyncio.to_thread(
                copy_rag_source_paths_to_mydata,
                paths,
                None,
            )
            status_txt.value = f"Copied n={n} file(s)."
            status_txt.update()
            page.update()

            copied_count["n"] = int(n or 0)

            if copied_count["n"] > 0:
                toast(
                    f"Copied {copied_count['n']} files. Click Update (index) to index."
                )
                status_txt.value = f"Copied {copied_count['n']} file(s). Click Update (index) to index."
            else:
                toast("Copied 0 files.")
                status_txt.value = "Copied 0 files."

            status_txt.update()
            page.update()

        except Exception as e:
            copied_count["n"] = 0
            status_txt.value = str(e)[:200]
            toast(f"Error: {e}")
            status_txt.update()
            page.update()
        finally:
            _show_progress(False)

    pick_files_upload_section = (
        ft.Row(
            [ft.OutlinedButton("Pick files…", on_click=_pick_files_click)], spacing=8
        )
        if file_picker is not None
        else ft.Text(
            "File picker is not available here. Use Download from URL below.",
            size=11,
            color=ft.Colors.GREY_500,
        )
    )

    def _update_index_click() -> None:
        async def _task() -> None:
            await _start_index_update()

        page.run_task(_task)

    update_btn = ft.Button(
        "Update (index) in toolbar",
        on_click=_update_index_click,
    )

    upload_dialog_body = ft.Column(
        cast(
            list[ft.Control],
            [
                ft.Text(
                    "Supported: .pdf, .docx, .doc, .xlsx, .xls, .pptx, .ppt, .html, .md, .json",
                    size=11,
                    color=ft.Colors.GREY_500,
                ),
                pick_files_upload_section,
                ft.Container(height=8),
                update_btn,  # <-- added explicit index trigger
                ft.Container(height=8),
                url_tf,
                ft.Button("Download from URL to mydata", on_click=_add_from_url),
                ft.Container(height=8),
                progress_row,
                status_txt,
            ],
        ),
        tight=True,
        scroll=ft.ScrollMode.AUTO,
        width=440,
    )

    _upload_dlg_appended: list[bool] = [False]

    def _close_upload_dialog(_e: ft.ControlEvent | None = None) -> None:
        upload_dlg.open = False
        page.update()

    upload_dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Add documents"),
        content=ft.Container(content=upload_dialog_body, width=460),
        actions=[ft.TextButton("Close", on_click=_close_upload_dialog)],
    )

    def open_upload_dialog(_e: ft.ControlEvent) -> None:
        if not _upload_dlg_appended[0]:
            page.overlay.append(upload_dlg)
            _upload_dlg_appended[0] = True
        upload_dlg.open = True
        page.update()

    return upload_dlg, open_upload_dialog
