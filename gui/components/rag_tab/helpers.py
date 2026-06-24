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
from gui.utils.rag_update_handler import RagUpdateViaZmq
from rag.mydata_file_manager_ops import organize_mydata_root

RAG_DOC_SUFFIXES = {
    ".pdf",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".pptx",
    ".ppt",
    ".html",
    ".md",
    ".txt",
}
RAG_WORKFLOW_SUFFIXES = {".json"}
RAG_ADD_FOLDER_SUFFIXES = RAG_DOC_SUFFIXES | RAG_WORKFLOW_SUFFIXES

RAG_UPDATE_TIMEOUT_S = 6000.0
WORKFLOW_SERVER_ENDPOINT = "tcp://127.0.0.1:6667"
RESPONSE_ENDPOINT = "tcp://127.0.0.1:6677"
WORKFLOW_SERVER_ENDPOINT_2 = "tcp://127.0.0.1:6668"
RESPONSE_ENDPOINT_2 = "tcp://127.0.0.1:6678"


def organize_mydata_root_files() -> int:
    """
    Move root-level files under configured ``mydata_dir`` into RAG layout.

    Same behavior as the ``MydataOrganize`` unit (``rag.mydata_file_manager_ops.organize_mydata_root``).
    Used before ``rag_update`` and after URL download without running the full refresh workflow.
    """
    return organize_mydata_root(get_mydata_dir())


def copy_rag_source_paths_to_mydata(
    source_paths: list[Path], source_root: Path | None = None
) -> int:
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
    Run ``rag_update`` workflow via ZMQ (RagUpdateViaZmq).
    Optionally show indexing state in dialog controls; always ``toast`` outcomes.
    """
    use_dialog_ui = dialog_status is not None and dialog_progress_row is not None
    if use_dialog_ui:
        if dialog_status is not None:
            dialog_status.value = "Indexing..."
        if dialog_progress_row is not None:
            dialog_progress_row.visible = True
            dialog_progress_row.update()
        page.update()

    try:
        await asyncio.to_thread(organize_mydata_root_files)
    except Exception:
        pass

    # You likely already have these somewhere; wire them up to your env/config.
    pub_endpoint = WORKFLOW_SERVER_ENDPOINT  # <- implement/replace
    sub_endpoint = RESPONSE_ENDPOINT  # <- implement/replace

    zmq_client = RagUpdateViaZmq(
        pub_endpoint=pub_endpoint,
        sub_endpoint=sub_endpoint,
        response_timeout_s=6000.0,  # keep consistent with your component default / run_workflow timeout
    )

    try:
        result = await zmq_client.run(
            workflow_path=str(get_rag_update_workflow_path()),
            initial_inputs=None,
            unit_param_overrides=build_rag_update_overrides_public(),
            format="dict",
        )

        # Component contract:
        # - success: {"response": <rag_update output dict>, "outputs": <raw outputs>}
        # - error:   {"error": "<message>", "payload": <raw error payload>}
        if result.get("error") is not None:
            msg = str(result.get("error") or "Update failed.")
            if use_dialog_ui and dialog_status is not None:
                dialog_status.value = msg[:300] if msg else "Update failed."
            toast(msg or "Update failed.")
            return

        response = result.get("response") or {}
        # This matches your previous extraction style:
        data = (response.get("rag_update") or {}).get("data") or {}

        ok = data.get("ok", False)
        msg = data.get("message", "") or data.get("error", "")
        units_count = data.get("units_count", 0)
        mydata_count = data.get("mydata_count", 0)

        if ok:
            if use_dialog_ui and dialog_status is not None:
                dialog_status.value = (
                    f"Index updated. units: {units_count}, mydata: {mydata_count}."
                )
            toast(f"Index updated. units: {units_count}, mydata: {mydata_count}.")
        else:
            if use_dialog_ui and dialog_status is not None:
                dialog_status.value = msg[:300] if msg else "Update failed."
            toast(msg or "Update failed.")

    except Exception as e:
        if use_dialog_ui and dialog_status is not None:
            dialog_status.value = str(e)[:200]
            toast(f"Error: {e}")
        if (
            use_dialog_ui
            and dialog_progress_row is not None
            and dialog_status is not None
        ):
            dialog_progress_row.visible = False
            dialog_status.update()
            dialog_progress_row.update()
        page.update()
    finally:
        await zmq_client.close()


async def run_rag_file_pick_copy_and_index(
    page: ft.Page,
    *,
    on_status: Callable[[str], None] | None = None,
    on_progress: Callable[[bool], None] | None = None,
) -> None:
    """
    Pick files (desktop), copy supported types to mydata, run rag_update — same flow as RAG tab.
    Uses RagUpdateViaZmq instead of running the workflow directly.
    """

    def toast(msg: str) -> None:
        if on_status:
            on_status(msg)
        else:
            p: Any = page
            p.snack_bar = ft.SnackBar(content=ft.Text(msg), open=True)
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

    zmq_client = None
    try:
        # add your endpoint getters here (as discussed)
        pub_endpoint = WORKFLOW_SERVER_ENDPOINT_2  # <- implement/replace
        sub_endpoint = RESPONSE_ENDPOINT_2  # <- implement/replace

        zmq_client = RagUpdateViaZmq(
            pub_endpoint=pub_endpoint,
            sub_endpoint=sub_endpoint,
            response_timeout_s=6000.0,
        )

        result = await zmq_client.run(
            workflow_path=str(get_rag_update_workflow_path()),
            initial_inputs=None,
            unit_param_overrides=build_rag_update_overrides_public(),
            format="dict",
        )

        if result.get("error") is not None:
            toast(
                str(result.get("error") or "Update failed.")[:300] or "Update failed."
            )
            return

        response = result.get("response") or {}
        data = (response.get("rag_update") or {}).get("data") or {}

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
    finally:
        progress(False)
        if zmq_client is not None:
            await zmq_client.close()
        try:
            page.update()
        except Exception:
            pass
