"""
RAG tab: upload files (folder, pick, or URL) into mydata_dir; index via rag_update workflow.

Upload actions copy or download files into mydata_dir only. Click "Update" to run
rag_update.json and index units_dir + mydata_dir.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

import flet as ft

from gui.flet.components.settings import (
    get_rag_embedding_model,
    get_rag_index_dir,
    get_rag_update_workflow_path,
    get_mydata_dir,
)
from gui.flet.tools.file_picker import register_file_picker
from runtime.run import run_workflow

RAG_DOC_SUFFIXES = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".html", ".md"}
RAG_WORKFLOW_SUFFIXES = {".json"}
RAG_ADD_FOLDER_SUFFIXES = RAG_DOC_SUFFIXES | RAG_WORKFLOW_SUFFIXES


def build_rag_tab(page: ft.Page) -> ft.Control:
    """
    Build the RAG tab: upload files (folder / pick / URL) into mydata_dir;
    run rag_update workflow via Update button to index units_dir + mydata_dir.
    """
    status_txt = ft.Text("", size=12, color=ft.Colors.GREY_400)
    progress_row = ft.Row(
        [ft.ProgressRing(width=20, height=20), ft.Text("Indexing...", size=12)],
        visible=False,
        spacing=8,
    )
    url_tf = ft.TextField(
        label="URL (workflows, catalogue, documents)",
        hint_text="e.g. https://example.com/workflow.json",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )

    def _toast(msg: str) -> None:
        page.snack_bar = ft.SnackBar(content=ft.Text(msg), open=True)
        page.update()

    def _show_progress(show: bool) -> None:
        progress_row.visible = show
        progress_row.update()
        page.update()

    def _copy_paths_to_mydata(source_paths: list[Path], source_root: Path | None = None) -> int:
        """Copy files into mydata_dir. If source_root is set, preserve relative path under it; else flatten by name (dedupe by adding _1, _2). Returns number of files copied."""
        mydata = get_mydata_dir()
        mydata.mkdir(parents=True, exist_ok=True)
        n = 0
        for src in source_paths:
            if not src.is_file():
                continue
            if source_root is not None:
                try:
                    rel = src.resolve().relative_to(source_root.resolve())
                except ValueError:
                    rel = src.name
            else:
                rel = src.name
            dest = mydata / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest == src:
                continue
            counter = 0
            stem, suffix = dest.stem, dest.suffix
            while dest.exists() and dest.resolve() != src.resolve():
                counter += 1
                dest = dest.parent / f"{stem}_{counter}{suffix}"
            shutil.copy2(src, dest)
            n += 1
        return n

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
            status_txt.value = f"Downloaded to mydata. Click Update to index."
            _toast("Downloaded. Click Update to index.")
        except Exception as e:
            status_txt.value = str(e)[:200]
            _toast(f"Error: {e}")
        _show_progress(False)
        status_txt.update()
        page.update()

    def _add_from_url(_e: ft.ControlEvent) -> None:
        raw = (url_tf.value or "").strip()
        if not raw:
            _toast("Enter a URL.")
            return
        if not raw.startswith(("http://", "https://")):
            _toast("URL must start with http:// or https://")
            return
        async def _url_task() -> None:
            await _download_url_to_mydata(raw)
        page.run_task(_url_task)

    def _build_rag_update_overrides() -> dict[str, dict[str, Any]]:
        return {
            "rag_update": {
                "rag_index_data_dir": str(get_rag_index_dir()),
                "mydata_dir": str(get_mydata_dir()),
                "units_dir": "units",
                "embedding_model": get_rag_embedding_model(),
            },
        }

    async def _run_update_workflow_async() -> None:
        status_txt.value = "Indexing..."
        _show_progress(True)
        try:
            out = await asyncio.to_thread(
                run_workflow,
                get_rag_update_workflow_path(),
                initial_inputs=None,
                unit_param_overrides=_build_rag_update_overrides(),
                format="dict",
                execution_timeout_s=600.0,
            )
            data = (out.get("rag_update") or {}).get("data") or {}
            ok = data.get("ok", False)
            msg = data.get("message", "") or data.get("error", "")
            units_count = data.get("units_count", 0)
            mydata_count = data.get("mydata_count", 0)
            if ok:
                status_txt.value = f"Index updated. units: {units_count}, mydata: {mydata_count}."
                _toast(f"Index updated. units: {units_count}, mydata: {mydata_count}.")
            else:
                status_txt.value = msg[:300] if msg else "Update failed."
                _toast(msg or "Update failed.")
        except Exception as e:
            status_txt.value = str(e)[:200]
            _toast(f"Error: {e}")
        _show_progress(False)
        status_txt.update()
        page.update()

    def _update_click(_e: ft.ControlEvent) -> None:
        page.run_task(_run_update_workflow_async)

    def _clear_click(_e: ft.ControlEvent) -> None:
        idx_dir = get_rag_index_dir()
        try:
            if idx_dir.exists():
                shutil.rmtree(idx_dir)
                status_txt.value = "RAG index cleared."
                _toast("RAG index cleared.")
            else:
                status_txt.value = "No index to clear."
                _toast("No index to clear.")
        except OSError as err:
            status_txt.value = str(err)[:200]
            _toast(f"Error: {err}")
        status_txt.update()
        page.update()

    # FilePicker: per docs.flet.dev/services/filepicker — await pick_files() for result.
    file_picker = register_file_picker(page)

    async def _pick_files_and_copy() -> None:
        if not file_picker:
            _toast("File picker not available. Use folder path or URL.")
            return
        try:
            files = await file_picker.pick_files(allow_multiple=True)
        except Exception as e:
            _toast(f"File picker error: {e}")
            return
        if not files:
            return
        paths = []
        for f in files:
            path = getattr(f, "path", None)
            if not path and getattr(f, "name", None):
                _toast("Selected files are not available as paths (e.g. in browser). Use folder path or URL.")
                return
            if path and Path(path).is_file():
                p = Path(path)
                if p.suffix.lower() in RAG_ADD_FOLDER_SUFFIXES:
                    paths.append(p)
        if paths:
            status_txt.value = "Copying to mydata..."
            _show_progress(True)
            try:
                n = await asyncio.to_thread(_copy_paths_to_mydata, paths, None)
                status_txt.update()
                page.update()
                if n > 0:
                    await _run_update_workflow_async()
                else:
                    status_txt.value = "Copied 0 files."
                    _show_progress(False)
                    status_txt.update()
                    page.update()
            except Exception as e:
                status_txt.value = str(e)[:200]
                _toast(f"Error: {e}")
                _show_progress(False)
                status_txt.update()
                page.update()
        else:
            _toast("No supported files selected (e.g. .pdf, .md, .json).")

    def _pick_files_click(_e: ft.ControlEvent) -> None:
        if file_picker:
            page.run_task(_pick_files_and_copy)

    pick_files_row = (
        ft.Row([ft.OutlinedButton("Pick files…", on_click=_pick_files_click)], spacing=8)
        if file_picker is not None
        else ft.Container()
    )

    return ft.Container(
        content=ft.Column(
            [
                ft.Text("RAG", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Add documents to the knowledge base used by Workflow Designer and RL Coach.",
                    size=12,
                    color=ft.Colors.GREY_500,
                ),
                ft.Container(height=16),
                ft.Text("Supported: .pdf, .docx, .doc, .xlsx, .xls, .pptx, .ppt, .html, .md, .json", size=11, color=ft.Colors.GREY_400),
                ft.Container(height=12),
                pick_files_row,
                ft.Container(height=12),
                url_tf,
                ft.ElevatedButton("Upload from URL", on_click=_add_from_url),
                ft.Container(height=12),
                progress_row,
                status_txt,
                ft.Container(height=12),
                ft.Row(
                    [
                        ft.ElevatedButton("Update", on_click=_update_click),
                        ft.OutlinedButton("Clear RAG index", on_click=_clear_click),
                    ],
                    spacing=8,
                ),
            ],
            spacing=6,
            alignment=ft.MainAxisAlignment.START,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=24,
        expand=True,
    )
