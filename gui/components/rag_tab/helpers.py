"""
Shared RAG tab helpers: copy to mydata, rag_update overrides, chat file pick + index.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any, Callable

import flet as ft

from gui.components.settings import (
    get_mydata_dir,
    get_rag_embedding_model,
    get_rag_index_dir,
    get_rag_update_workflow_path,
)
from gui.utils.file_picker import register_file_picker
from rag.mydata_file_manager_ops import organize_mydata_root
from runtime.run import run_workflow

RAG_DOC_SUFFIXES = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".html", ".md"}
RAG_WORKFLOW_SUFFIXES = {".json"}
RAG_ADD_FOLDER_SUFFIXES = RAG_DOC_SUFFIXES | RAG_WORKFLOW_SUFFIXES

def organize_mydata_root_files() -> int:
    """
    Move root-level files under configured ``mydata_dir`` into RAG layout.

    Same behavior as the ``MydataOrganize`` unit (``rag.mydata_file_manager_ops.organize_mydata_root``).
    Used before ``rag_update`` and after URL download without running the full refresh workflow.
    """
    return organize_mydata_root(get_mydata_dir())


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
    """Unit param overrides for ``rag/workflows/rag_update.json`` (shared with RAG tab and chat upload)."""
    return {
        "rag_update": {
            "rag_index_data_dir": str(get_rag_index_dir()),
            "mydata_dir": str(get_mydata_dir()),
            "units_dir": "units",
            "embedding_model": get_rag_embedding_model(),
        },
    }


async def run_rag_index_update_async(
    page: ft.Page,
    toast: Callable[[str], None],
    *,
    dialog_status: ft.Text | None = None,
    dialog_progress_row: ft.Row | None = None,
) -> None:
    """
    Run ``rag_update`` workflow. Optionally show indexing state in dialog controls; always ``toast`` outcomes.
    """
    use_dialog_ui = dialog_status is not None and dialog_progress_row is not None
    if use_dialog_ui:
        dialog_status.value = "Indexing..."
        dialog_progress_row.visible = True
        dialog_progress_row.update()
        page.update()
    try:
        await asyncio.to_thread(organize_mydata_root_files)
    except Exception:
        pass
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
            if use_dialog_ui:
                dialog_status.value = f"Index updated. units: {units_count}, mydata: {mydata_count}."
            toast(f"Index updated. units: {units_count}, mydata: {mydata_count}.")
        else:
            if use_dialog_ui:
                dialog_status.value = msg[:300] if msg else "Update failed."
            toast(msg or "Update failed.")
    except Exception as e:
        if use_dialog_ui:
            dialog_status.value = str(e)[:200]
        toast(f"Error: {e}")
    if use_dialog_ui:
        dialog_progress_row.visible = False
        dialog_status.update()
        dialog_progress_row.update()
    page.update()


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
        await asyncio.to_thread(organize_mydata_root_files)
    except Exception:
        pass
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
