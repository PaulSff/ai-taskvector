"""
Dialog to view/edit the process graph as JSON in a code editor.
"""
from __future__ import annotations

import json

import flet as ft

from schemas.process_graph import ProcessGraph

from gui.flet.components.workflow.code_editor import build_code_editor


def open_view_graph_code_dialog(
    page: ft.Page,
    graph: ProcessGraph | None,
) -> None:
    """Open a modal dialog showing the current graph as JSON in an editable code view."""
    try:
        if graph is None:
            json_str = "{}"
        else:
            json_str = json.dumps(
                graph.model_dump(by_alias=True), indent=2
            )
    except Exception as ex:
        json_str = f'{{"error": {json.dumps(str(ex))}}}'

    def _close_dlg() -> None:
        dlg.open = False
        page.update()

    # Width of the scrollable/editable area where the code is displayed
    editor_width = 560
    code_editor_control, _get_value = build_code_editor(
        code=json_str, height=400, width=editor_width
    )
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Graph (code)"),
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text("Graph JSON", size=12, color=ft.Colors.GREY_500),
                    code_editor_control,
                ],
                spacing=8,
            ),
            width=editor_width,
        ),
        actions=[ft.TextButton("Close", on_click=lambda e: _close_dlg())],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
