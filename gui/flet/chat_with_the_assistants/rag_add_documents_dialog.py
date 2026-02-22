"""
Dialog to add documents to the RAG index.
Uses path entry (no FilePicker) for compatibility across Flet versions.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

import flet as ft

from gui.flet.components.settings import get_rag_embedding_model, get_rag_index_dir


RAG_DOC_SUFFIXES = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".html", ".md"}
RAG_WORKFLOW_SUFFIXES = {".json"}
RAG_ADD_FOLDER_SUFFIXES = RAG_DOC_SUFFIXES | RAG_WORKFLOW_SUFFIXES


def open_rag_add_documents_dialog(
    page: ft.Page,
    on_done: Callable[[str], None] | None = None,
) -> None:
    """
    Open a modal dialog to add documents to RAG.
    User enters a folder path; all supported documents in that folder are indexed.
    on_done: optional callback with status message (e.g. "Added 3 documents").
    """
    status_txt = ft.Text("", size=12, color=ft.Colors.GREY_400)
    progress_row = ft.Row(
        [ft.ProgressRing(width=20, height=20), ft.Text("Indexing...", size=12)],
        visible=False,
        spacing=8,
    )
    path_tf = ft.TextField(
        label="Folder path",
        value="mydata",
        hint_text="e.g. mydata or /path/to/documents",
        width=360,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    url_tf = ft.TextField(
        label="URL (workflows, catalogue, documents)",
        hint_text="e.g. https://example.com/workflow.json",
        width=360,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )

    def _close_dlg() -> None:
        dlg.open = False
        page.update()

    def _toast(msg: str) -> None:
        page.snack_bar = ft.SnackBar(content=ft.Text(msg), open=True)
        page.update()

    def _show_progress(show: bool) -> None:
        progress_row.visible = show
        progress_row.update()
        page.update()

    async def _run_index_async(paths: list[Path]) -> None:
        if not paths:
            _toast("No supported files found.")
            return
        status_txt.value = "Indexing... (this may take a few minutes)"
        _show_progress(True)
        try:
            from rag.indexer import RAGIndex

            def _index() -> int:
                index = RAGIndex(
                    persist_dir=str(get_rag_index_dir()),
                    embedding_model=get_rag_embedding_model(),
                )
                return index.add_documents_and_index([str(p) for p in paths])

            n = await asyncio.to_thread(_index)
            status_txt.value = f"Added {n} document(s) to RAG index."
            _toast(f"Added {n} document(s) to RAG index.")
            if on_done:
                on_done(f"Added {n} document(s)")
        except ImportError as e:
            status_txt.value = "RAG dependencies not installed. Run: pip install -r requirements-rag.txt"
            _toast(str(e))
        except Exception as e:
            status_txt.value = str(e)[:200]
            _toast(f"Error: {e}")
        _show_progress(False)
        status_txt.update()
        page.update()

    def _add_from_path(_e: ft.ControlEvent) -> None:
        raw = (path_tf.value or "").strip()
        if not raw:
            _toast("Enter a folder path.")
            return
        p = Path(raw).expanduser().resolve()
        if not p.is_dir():
            _toast(f"Not a directory: {p}")
            return
        paths = [
            x for x in p.rglob("*")
            if x.is_file() and x.suffix.lower() in RAG_ADD_FOLDER_SUFFIXES
        ]
        if paths:
            page.run_task(_run_index_async(paths))
        else:
            _toast("No supported documents or JSON workflows in that folder.")

    async def _add_from_url_async(url: str) -> None:
        status_txt.value = "Fetching and indexing..."
        _show_progress(True)
        try:
            from rag.indexer import RAGIndex

            def _fetch() -> int:
                index = RAGIndex(
                    persist_dir=str(get_rag_index_dir()),
                    embedding_model=get_rag_embedding_model(),
                )
                return index.add_from_url_and_index(url)

            n = await asyncio.to_thread(_fetch)
            status_txt.value = f"Added {n} item(s) from URL."
            _toast(f"Added {n} item(s) from URL.")
        except ImportError:
            status_txt.value = "RAG dependencies not installed. Run: pip install -r requirements-rag.txt"
            _toast("RAG dependencies not installed.")
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
        page.run_task(_add_from_url_async(raw))

    def _add_click(e: ft.ControlEvent) -> None:
        _add_from_path(e)

    def _close_click(e: ft.ControlEvent) -> None:
        _close_dlg()

    def _clear_click(e: ft.ControlEvent) -> None:
        import shutil
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

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Add documents to RAG"),
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        ".pdf, .docx, .doc, .xlsx, .xls, .pptx, .ppt, .html, .md",
                        size=12,
                        color=ft.Colors.GREY_400,
                    ),
                    ft.Container(height=12),
                    path_tf,
                    ft.ElevatedButton("Add files from folder", on_click=_add_click),
                    ft.Container(height=12),
                    url_tf,
                    ft.ElevatedButton("Upload from URL", on_click=_add_from_url),
                    ft.Container(height=12),
                    progress_row,
                    status_txt,
                    ft.Row(
                        [
                            ft.TextButton("Clear", on_click=_clear_click),
                            ft.TextButton("Close", on_click=_close_click),
                        ],
                        spacing=8,
                    ),
                ],
                spacing=4,
                width=360,
            ),
        ),
        actions=[],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
