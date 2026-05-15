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

from assistants.tools.import_workflow import import_workflow_graph_path
from core.schemas.process_graph import ProcessGraph
from gui.utils.file_picker import register_file_picker

_WORKFLOW_DIR = Path(__file__).resolve().parent.parent
AUTO_IMPORT_WORKFLOW_PATH = (
    _WORKFLOW_DIR
    / "workflows"
    / "import_import_workflows"
    / "auto_import_workflow.json"
)
IMPORT_WORKFLOW_PATH = import_workflow_graph_path()
NEW_FLOW_TEMPLATE_PATH = (
    _WORKFLOW_DIR / "workflows" / "import_workflows" / "new_flow_template.json"
)


def run_auto_import_workflow(raw_data: dict | list) -> tuple[dict | None, str]:
    from runtime.run import run_workflow

    if not AUTO_IMPORT_WORKFLOW_PATH.exists():
        return (None, f"Workflow file not found: {AUTO_IMPORT_WORKFLOW_PATH}")
    initial_inputs = {"inject_graph": {"data": raw_data}}
    try:
        outputs = run_workflow(
            str(AUTO_IMPORT_WORKFLOW_PATH), initial_inputs=initial_inputs, format="dict"
        )
    except Exception as e:
        return (None, str(e))
    iw = (outputs or {}).get("import_workflow") or {}
    err = iw.get("error") or ""
    graph = iw.get("graph")
    return (graph, err or "")


IMPORT_FORMATS: list[tuple[str, str]] = [
    ("Auto", "auto"),
    ("Node-RED", "node_red"),
    ("Pyflow", "pyflow"),
    ("Ryven", "ryven"),
    ("n8n", "n8n"),
    ("Canonical Graph", "dict"),
]


def _show_snack(page: ft.Page, message: str) -> None:
    """Show a SnackBar in a typing-safe way without relying on unknown attributes."""
    snack = ft.SnackBar(content=ft.Text(message), open=True)
    try:
        setattr(page, "snack_bar", snack)  # type: ignore[attr-defined]
        page.update()
        return
    except Exception:
        pass

    try:
        # Avoid ft.padding/ft.margin helpers; use Container padding and alignment instead.
        temp = ft.Container(
            content=ft.Text(message, color=ft.Colors.WHITE),
            bgcolor="#323232",
            padding=8,
            border_radius=6,
            alignment=ft.alignment.Alignment(
                0, -1
            ),  # centered horizontally, top-aligned vertically
            width=page.width if getattr(page, "width", None) else None,
        )
        page.overlay.append(temp)
        page.update()

        async def _remove_after_delay():
            await asyncio.sleep(3.0)
            try:
                page.overlay.remove(temp)
                page.update()
            except Exception:
                pass

        asyncio.create_task(_remove_after_delay())
    except Exception:
        pass


def open_import_workflow_dialog(
    page: ft.Page,
    on_imported: Callable[[ProcessGraph], None],
) -> None:
    format_dropdown = ft.Dropdown(
        label="Format",
        options=[
            ft.dropdown.Option(key=fmt, text=label) for label, fmt in IMPORT_FORMATS
        ],
        value="auto",
        width=200,
    )
    editor_width = 520
    file_picker = register_file_picker(page)

    def _close_dlg() -> None:
        dlg.open = False
        page.update()

    def _raw_to_dict(raw: str | dict) -> dict | list:
        if isinstance(raw, str):
            return json.loads(raw)
        return raw

    def _run_import_workflow(raw_data: dict | list) -> tuple[dict | None, str]:
        from runtime.run import run_workflow

        fmt = format_dropdown.value or "auto"
        if fmt == "auto":
            return run_auto_import_workflow(raw_data)
        path = IMPORT_WORKFLOW_PATH
        initial_inputs = {"import_workflow": {"graph": raw_data, "origin": fmt}}
        if not path.exists():
            return (None, f"Workflow file not found: {path}")
        try:
            outputs = run_workflow(
                str(path), initial_inputs=initial_inputs, format="dict"
            )
        except Exception as e:
            return (None, str(e))
        iw = (outputs or {}).get("import_workflow") or {}
        err = iw.get("error") or ""
        graph = iw.get("graph")
        return (graph, err or "")

    async def _do_import_async(raw: str | dict) -> None:
        try:
            raw_data = _raw_to_dict(raw)
        except json.JSONDecodeError as e:
            _show_snack(page, f"Invalid JSON: {e}")
            return
        canonical, err = await asyncio.to_thread(_run_import_workflow, raw_data)
        if err and err.strip():
            _show_snack(page, err[:300])
            return
        if canonical is None:
            _show_snack(page, "Import failed (no graph returned)")
            return
        try:
            graph = ProcessGraph.model_validate(canonical)
        except Exception as e:
            _show_snack(page, str(e))
            return
        _close_dlg()
        on_imported(graph)

    async def _pick_file_and_import() -> None:
        if not file_picker:
            _show_snack(page, "File picker not available")
            return
        try:
            files = await file_picker.pick_files(allow_multiple=False)
        except Exception as e:
            _show_snack(page, f"File picker error: {e}")
            return
        if not files:
            return
        f = files[0]
        path = getattr(f, "path", None)
        if not path:
            _show_snack(page, "Selected file path not available (e.g. in browser)")
            return
        path = Path(path)
        if not path.is_file():
            _show_snack(page, "Selected path is not a file")
            return
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            _show_snack(page, f"Cannot read file: {e}")
            return
        try:
            data = json.loads(text)
            try:
                page.run_task(lambda: _do_import_async(data))
            except Exception:
                asyncio.create_task(_do_import_async(data))
        except json.JSONDecodeError as ex:
            _show_snack(page, f"Invalid JSON: {ex}")
        except Exception as ex:
            _show_snack(page, str(ex))

    def _open_file_click(e: object | None = None) -> None:
        try:
            page.run_task(lambda: _pick_file_and_import())
        except Exception:
            asyncio.create_task(_pick_file_and_import())

    def _import_from_paste(e: object | None = None) -> None:
        text = (paste_tf.value or "").strip()
        if not text:
            _show_snack(page, "Paste JSON first")
            return
        try:
            data = json.loads(text)
            try:
                page.run_task(lambda: _do_import_async(data))
            except Exception:
                asyncio.create_task(_do_import_async(data))
        except json.JSONDecodeError as ex:
            _show_snack(page, f"Invalid JSON: {ex}")
        except Exception as ex:
            _show_snack(page, str(ex))

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

    if file_picker:
        import_from_file_btn: ft.Control = ft.OutlinedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.FOLDER_OPEN, size=18),
                    ft.Text("Import from file"),
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            on_click=lambda e=None: _open_file_click(e),
        )
    else:
        import_from_file_btn = ft.Container()

    import_button = ft.TextButton(
        "Import", on_click=lambda e=None: _import_from_paste(e)
    )

    content_col = ft.Column(
        controls=[
            format_dropdown,
            ft.Container(height=12),
            ft.Text("Paste JSON below", size=12, color=ft.Colors.GREY_600),
            paste_input_container,
            import_button,
            import_from_file_btn,
        ],
        spacing=8,
        width=editor_width + 24,
    )

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Import workflow"),
        content=ft.Container(content=content_col, width=editor_width + 24),
        actions=[ft.TextButton("Cancel", on_click=lambda e=None: _close_dlg())],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
