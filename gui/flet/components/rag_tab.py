"""
RAG tab: upload files (folder, pick, or URL) into mydata_dir; index via rag_update workflow.

Upload actions copy or download files into mydata_dir only. Click "Update" to run
rag_update.json and index units_dir + mydata_dir.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any, Callable

import flet as ft

from assistants.roles import WORKFLOW_DESIGNER_ROLE_ID
from gui.flet.chat_with_the_assistants.rag_context import get_rag_context, get_rag_context_by_path
from gui.flet.components.settings import (
    get_rag_embedding_model,
    get_rag_index_dir,
    get_rag_update_workflow_path,
    get_mydata_dir,
)
from gui.flet.utils.file_picker import register_file_picker
from runtime.run import run_workflow

RAG_DOC_SUFFIXES = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".html", ".md"}
RAG_WORKFLOW_SUFFIXES = {".json"}
RAG_ADD_FOLDER_SUFFIXES = RAG_DOC_SUFFIXES | RAG_WORKFLOW_SUFFIXES


def copy_rag_source_paths_to_mydata(source_paths: list[Path], source_root: Path | None = None) -> int:
    """
    Copy files into mydata_dir (same rules as the RAG tab).
    If source_root is set, preserve relative path under it; else flatten by basename (dedupe).
    Returns number of files copied.
    """
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


def build_rag_update_overrides_public() -> dict[str, dict[str, Any]]:
    """Unit param overrides for rag_update.json (shared with RAG tab and chat upload)."""
    return {
        "rag_update": {
            "rag_index_data_dir": str(get_rag_index_dir()),
            "mydata_dir": str(get_mydata_dir()),
            "units_dir": "units",
            "embedding_model": get_rag_embedding_model(),
        },
    }


async def run_rag_file_pick_copy_and_index(
    page: ft.Page,
    *,
    on_status: Callable[[str], None] | None = None,
    on_progress: Callable[[bool], None] | None = None,
) -> None:
    """
    Pick files (desktop), copy supported types to mydata, run rag_update — same flow as RAG tab.
    """

    def toast(msg: str) -> None:
        if on_status:
            on_status(msg)
        else:
            page.snack_bar = ft.SnackBar(content=ft.Text(msg), open=True)
            page.update()

    def progress(show: bool) -> None:
        if on_progress:
            on_progress(show)

    fp = register_file_picker(page)
    if not fp:
        toast("File picker not available. Use folder path or URL.")
        return
    try:
        files = await fp.pick_files(allow_multiple=True)
    except Exception as e:
        toast(f"File picker error: {e}")
        return
    if not files:
        return
    paths: list[Path] = []
    for f in files:
        path = getattr(f, "path", None)
        if not path and getattr(f, "name", None):
            toast("Selected files are not available as paths (e.g. in browser). Use folder path or URL.")
            return
        if path and Path(path).is_file():
            p = Path(path)
            if p.suffix.lower() in RAG_ADD_FOLDER_SUFFIXES:
                paths.append(p)
    if not paths:
        toast("No supported files selected (e.g. .pdf, .md, .json).")
        return
    toast("Copying to mydata...")
    progress(True)
    try:
        n = await asyncio.to_thread(copy_rag_source_paths_to_mydata, paths, None)
    except Exception as e:
        progress(False)
        toast(f"Error: {e}")
        return
    if n <= 0:
        progress(False)
        toast("Copied 0 files.")
        return
    toast("Indexing…")
    try:
        out = await asyncio.to_thread(
            run_workflow,
            get_rag_update_workflow_path(),
            initial_inputs=None,
            unit_param_overrides=build_rag_update_overrides_public(),
            format="dict",
            execution_timeout_s=600.0,
        )
        data = (out.get("rag_update") or {}).get("data") or {}
        ok = data.get("ok", False)
        msg = data.get("message", "") or data.get("error", "")
        units_count = data.get("units_count", 0)
        mydata_count = data.get("mydata_count", 0)
        if ok:
            toast(f"Index updated. units: {units_count}, mydata: {mydata_count}.")
        else:
            toast(msg[:300] if msg else "Update failed.")
    except Exception as e:
        toast(f"Error: {e}")
    progress(False)
    try:
        page.update()
    except Exception:
        pass


def build_rag_tab(page: ft.Page, show_rag_preview: bool = False) -> ft.Control:
    """
    Build the RAG tab: upload files (folder / pick / URL) into mydata_dir;
    run rag_update workflow via Update button to index units_dir + mydata_dir.
    When show_rag_preview is True (dev mode), show a RAG context preview section.
    """
    status_txt = ft.Text("", size=12, color=ft.Colors.GREY_400)
    progress_row = ft.Row(
        [ft.ProgressRing(width=20, height=20), ft.Text("Indexing...", size=12)],
        visible=False,
        spacing=8,
    )
    url_tf = ft.TextField(
        label="URL",
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
        """Copy files into mydata_dir (delegates to shared helper)."""
        return copy_rag_source_paths_to_mydata(source_paths, source_root)

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
        return build_rag_update_overrides_public()

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

    # Dev: RAG context preview — runs rag_context_workflow (rag_search → rag_filter → format_rag)
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
                ft.Text("Optional: top_k (search), max_chars, snippet_max. Leave blank for defaults.", size=10, color=ft.Colors.GREY_600),
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
                ft.Container(height=16),
                dev_rag_section,
            ],
            spacing=6,
            alignment=ft.MainAxisAlignment.START,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=24,
        expand=True,
    )
