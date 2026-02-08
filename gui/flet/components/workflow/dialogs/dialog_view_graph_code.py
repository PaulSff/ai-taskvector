"""
Dialog to view/edit the process graph as JSON in a code editor.
"""
from __future__ import annotations

import json
from typing import Callable

import flet as ft

from schemas.process_graph import Connection, ProcessGraph, Unit

from gui.flet.components.workflow.dialogs.dialog_common import dict_to_graph
from gui.flet.tools.code_editor import build_code_editor
from gui.flet.tools.notifications import show_toast


def open_view_graph_code_dialog(
    page: ft.Page,
    graph: ProcessGraph | None,
    *,
    unit_id: str | None = None,
    on_graph_saved: Callable[[ProcessGraph], None] | None = None,
) -> None:
    """Open a modal dialog showing graph as JSON. If unit_id is set, show only that node and its connections.
    on_graph_saved: called when Apply or Delete is used so the caller can update the graph and refresh."""
    try:
        if graph is None:
            json_str = "{}"
        elif unit_id is not None:
            unit = graph.get_unit(unit_id)
            if unit is None:
                json_str = f'{{"error": "Unit {json.dumps(unit_id)} not found"}}'
            else:
                connections = [
                    c.model_dump(by_alias=True)
                    for c in graph.connections
                    if c.from_id == unit_id or c.to_id == unit_id
                ]
                filtered = {
                    "unit": unit.model_dump(by_alias=True),
                    "connections": connections,
                }
                json_str = json.dumps(filtered, indent=2)
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
    code_editor_control, get_value = build_code_editor(
        code=json_str, height=400, width=editor_width
    )
    title = ft.Text("Node (code)" if unit_id else "Graph (code)")

    def apply_click(_e: ft.ControlEvent) -> None:
        if on_graph_saved is None or graph is None:
            return
        try:
            text = get_value()
            data = json.loads(text)
            if unit_id is not None:
                if "error" in data:
                    page.snack_bar = ft.SnackBar(content=ft.Text("Cannot apply error payload"), open=True)
                    page.update()
                    return
                unit_data = data.get("unit")
                conns_data = data.get("connections", [])
                if not unit_data:
                    page.snack_bar = ft.SnackBar(content=ft.Text("Missing 'unit' in JSON"), open=True)
                    page.update()
                    return
                updated_unit = Unit.model_validate(unit_data)
                new_units = [u for u in graph.units if u.id != unit_id] + [updated_unit]
                new_connections = [
                    c for c in graph.connections
                    if c.from_id != unit_id and c.to_id != unit_id
                ] + [Connection.model_validate(c) for c in conns_data]
                new_graph = ProcessGraph(
                    environment_type=graph.environment_type,
                    units=new_units,
                    connections=new_connections,
                    code_blocks=graph.code_blocks,
                )
            else:
                new_graph = dict_to_graph(data)
            on_graph_saved(new_graph)
            _close_dlg()
        except Exception as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(str(ex)), open=True)
            page.update()

    async def copy_click(_e: ft.ControlEvent) -> None:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            await page.clipboard.set(get_value())
        await show_toast(page, "Copied!")

    def delete_click(_e: ft.ControlEvent) -> None:
        if on_graph_saved is None or graph is None or unit_id is None:
            return
        new_units = [u for u in graph.units if u.id != unit_id]
        new_connections = [
            c for c in graph.connections
            if c.from_id != unit_id and c.to_id != unit_id
        ]
        new_graph = ProcessGraph(
            environment_type=graph.environment_type,
            units=new_units,
            connections=new_connections,
            code_blocks=graph.code_blocks,
        )
        on_graph_saved(new_graph)
        _close_dlg()

    left_buttons: list[ft.Control] = []
    if on_graph_saved is not None and graph is not None:
        left_buttons.append(ft.TextButton("Apply", on_click=apply_click))
    if unit_id is not None and on_graph_saved is not None and graph is not None:
        left_buttons.append(ft.TextButton("Delete", on_click=delete_click))

    dlg = ft.AlertDialog(
        modal=True,
        title=title,
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Row(
                            [
                                *left_buttons,
                                ft.Container(expand=True),
                                ft.IconButton(
                                    icon=ft.Icons.COPY,
                                    tooltip="Copy to clipboard",
                                    on_click=copy_click,
                                    icon_color=ft.Colors.PRIMARY,
                                ),
                            ],
                            spacing=8,
                        ),
                        bgcolor="#121212",
                        padding=8,
                    ),
                    ft.Text("Graph JSON", size=12, color=ft.Colors.GREY_400),
                    code_editor_control,
                ],
                spacing=8,
            ),
            width=editor_width,
            bgcolor="#121212",
        ),
        actions=[ft.TextButton("Close", on_click=lambda e: _close_dlg())],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
