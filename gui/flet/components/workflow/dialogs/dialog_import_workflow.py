"""
Dialog to import a workflow from Node-RED, Pyflow, Ryven, or Process graph JSON.
Paste JSON into the editor and click Import, or use Open file to pick a workflow file.
Format "Auto" runs auto_import_workflow (RagDetectOrigin -> Import_workflow); other options run import_workflow with origin.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable

import flet as ft

from core.schemas.process_graph import ProcessGraph

from gui.flet.tools.file_picker import register_file_picker

_WORKFLOW_DIR = Path(__file__).resolve().parent.parent
AUTO_IMPORT_WORKFLOW_PATH = _WORKFLOW_DIR / "auto_import_workflow.json"
IMPORT_WORKFLOW_PATH = _WORKFLOW_DIR / "import_workflow.json"

IMPORT_FORMATS: list[tuple[str, str]] = [
    ("Auto", "auto"),
    ("Node-RED", "node_red"),
    ("Pyflow", "pyflow"),
    ("Ryven", "ryven"),
    ("n8n", "n8n"),
    ("Process graph", "dict"),
]


def open_import_workflow_dialog(
    page: ft.Page,
    on_imported: Callable[[ProcessGraph], None],
) -> None:
    """Open a modal dialog to import a workflow by pasting JSON or picking a file. On success calls on_imported(graph)."""
    format_dropdown = ft.Dropdown(
        label="Format",
        options=[ft.dropdown.Option(key=fmt, text=label) for label, fmt in IMPORT_FORMATS],
        value="auto",
        width=200,
    )
    editor_width = 520
    file_picker = register_file_picker(page)

    def _close_dlg() -> None:
        dlg.open = False
        page.update()

    def _raw_to_dict(raw: str | dict) -> dict | list:
        """Normalize to dict or list for workflow input."""
        if isinstance(raw, str):
            return json.loads(raw)
        return raw

    def _run_import_workflow(raw_data: dict | list) -> tuple[dict | None, str]:
        """Run auto_import or import_workflow; return (canonical_dict, error_msg)."""
        from runtime.run import run_workflow

        fmt = format_dropdown.value or "auto"
        if fmt == "auto":
            path = AUTO_IMPORT_WORKFLOW_PATH
            initial_inputs = {"inject_graph": {"data": raw_data}}
        else:
            path = IMPORT_WORKFLOW_PATH
            initial_inputs = {"import_workflow": {"graph": raw_data, "origin": fmt}}
        if not path.exists():
            return (None, f"Workflow file not found: {path}")
        try:
            outputs = run_workflow(str(path), initial_inputs=initial_inputs, format="dict")
        except Exception as e:
            return (None, str(e))
        iw = (outputs or {}).get("import_workflow") or {}
        err = iw.get("error") or ""
        graph = iw.get("graph")
        return (graph, err or "")

    async def _do_import_async(raw: str | dict) -> None:
        """Run workflow in thread then apply result on UI."""
        try:
            raw_data = _raw_to_dict(raw)
        except json.JSONDecodeError as e:
            page.snack_bar = ft.SnackBar(content=ft.Text(f"Invalid JSON: {e}"), open=True)
            page.update()
            return
        canonical, err = await asyncio.to_thread(_run_import_workflow, raw_data)
        if err and err.strip():
            page.snack_bar = ft.SnackBar(content=ft.Text(err[:300]), open=True)
            page.update()
            return
        if canonical is None:
            page.snack_bar = ft.SnackBar(content=ft.Text("Import failed (no graph returned)"), open=True)
            page.update()
            return
        try:
            graph = ProcessGraph.model_validate(canonical)
        except Exception as e:
            page.snack_bar = ft.SnackBar(content=ft.Text(str(e)), open=True)
            page.update()
            return
        _close_dlg()
        on_imported(graph)

    async def _pick_file_and_import() -> None:
        if not file_picker:
            page.snack_bar = ft.SnackBar(content=ft.Text("File picker not available"), open=True)
            page.update()
            return
        try:
            files = await file_picker.pick_files(allow_multiple=False)
        except Exception as e:
            page.snack_bar = ft.SnackBar(content=ft.Text(f"File picker error: {e}"), open=True)
            page.update()
            return
        if not files:
            return
        f = files[0]
        path = getattr(f, "path", None)
        if not path:
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Selected file path not available (e.g. in browser)"),
                open=True,
            )
            page.update()
            return
        path = Path(path)
        if not path.is_file():
            page.snack_bar = ft.SnackBar(content=ft.Text("Selected path is not a file"), open=True)
            page.update()
            return
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            page.snack_bar = ft.SnackBar(content=ft.Text(f"Cannot read file: {e}"), open=True)
            page.update()
            return
        try:
            data = json.loads(text)
            await _do_import_async(data)
        except json.JSONDecodeError as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(f"Invalid JSON: {ex}"), open=True)
            page.update()
        except Exception as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(str(ex)), open=True)
            page.update()

    def _open_file_click(_e: ft.ControlEvent) -> None:
        page.run_task(_pick_file_and_import)

    def _import_from_paste(_e: ft.ControlEvent) -> None:
        text = (paste_tf.value or "").strip()
        if not text:
            page.snack_bar = ft.SnackBar(content=ft.Text("Paste JSON first"), open=True)
            page.update()
            return
        try:
            data = json.loads(text)
            page.run_task(lambda: _do_import_async(data))
        except json.JSONDecodeError as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(f"Invalid JSON: {ex}"), open=True)
            page.update()
        except Exception as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(str(ex)), open=True)
            page.update()

    paste_tf = ft.TextField(
        value="",
        multiline=True,
        min_lines=10,
        max_lines=16,
        width=editor_width,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    paste_input_container = ft.Container(
        content=paste_tf,
        bgcolor="#12161A",
        border_radius=4,
    )

    import_from_file_btn = (
        ft.OutlinedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.FOLDER_OPEN, size=18),
                    ft.Text("Import from file"),
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            on_click=_open_file_click,
        )
        if file_picker
        else ft.Container()
    )
    content_col = ft.Column(
        [
            format_dropdown,
            ft.Container(height=12),
            ft.Text("Paste JSON below", size=12, color=ft.Colors.GREY_600),
            paste_input_container,
            ft.TextButton("Import", on_click=_import_from_paste),
            import_from_file_btn,
        ],
        spacing=8,
        width=editor_width + 24,
    )
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Import workflow"),
        content=ft.Container(
            content=content_col,
            width=editor_width + 24,
        ),
        actions=[ft.TextButton("Cancel", on_click=lambda e: _close_dlg())],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
