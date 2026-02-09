"""
Dialog to import a workflow from Node-RED, Pyflow, Ryven, or Process graph JSON.
Paste JSON into the editor and click Import.
"""
from __future__ import annotations

import json
from typing import Callable

import flet as ft

from normalizer.normalizer import FormatProcess, to_process_graph
from schemas.process_graph import ProcessGraph

IMPORT_FORMATS: list[tuple[str, FormatProcess]] = [
    ("Node-RED", "node_red"),
    ("Pyflow", "pyflow"),
    ("Ryven", "ryven"),
    ("Process graph", "dict"),
]


def open_import_workflow_dialog(
    page: ft.Page,
    on_imported: Callable[[ProcessGraph], None],
) -> None:
    """Open a modal dialog to import a workflow by pasting JSON. On success calls on_imported(graph)."""
    format_dropdown = ft.Dropdown(
        label="Format",
        options=[ft.dropdown.Option(key=fmt, text=label) for label, fmt in IMPORT_FORMATS],
        value="node_red",
        width=200,
    )
    editor_width = 520

    def _close_dlg() -> None:
        dlg.open = False
        page.update()

    def _do_import(raw: str | dict) -> None:
        fmt = format_dropdown.value or "node_red"
        if fmt == "dict":
            if isinstance(raw, str):
                data = json.loads(raw)
            else:
                data = raw
            graph = to_process_graph(data, format="dict")
        else:
            graph = to_process_graph(raw, format=fmt)
        _close_dlg()
        on_imported(graph)

    def _import_from_paste(_e: ft.ControlEvent) -> None:
        text = (paste_tf.value or "").strip()
        if not text:
            page.snack_bar = ft.SnackBar(content=ft.Text("Paste JSON first"), open=True)
            page.update()
            return
        try:
            data = json.loads(text)
            _do_import(data)
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

    content_col = ft.Column(
        [
            format_dropdown,
            ft.Container(height=12),
            ft.Text("Paste JSON below", size=12, color=ft.Colors.GREY_600),
            paste_tf,
            ft.TextButton("Import", on_click=_import_from_paste),
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
            bgcolor="#12161A",
        ),
        actions=[ft.TextButton("Cancel", on_click=lambda e: _close_dlg())],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
