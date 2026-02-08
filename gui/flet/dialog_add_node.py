"""
Dialog to add a node (unit) to the process graph.
"""
from __future__ import annotations

from typing import Callable

import flet as ft

from schemas.process_graph import ProcessGraph

from gui.flet.dialog_common import dict_to_graph, graph_to_dict

UNIT_TYPES = ["Source", "Valve", "Tank", "Sensor"]


def open_add_node_dialog(
    page: ft.Page,
    current_graph: ProcessGraph | None,
    on_saved: Callable[[ProcessGraph], None],
) -> None:
    """Open dialog to add a new unit (node). On Save calls on_saved(new_graph)."""
    from assistants.graph_edits import apply_graph_edit

    id_field = ft.TextField(label="Id", hint_text="e.g. my_valve", autofocus=True)
    type_dropdown = ft.Dropdown(
        label="Type",
        options=[ft.dropdown.Option(t) for t in UNIT_TYPES],
        value=UNIT_TYPES[1],
    )
    controllable_check = ft.Checkbox(label="Controllable", value=False)

    def save(_e: ft.ControlEvent) -> None:
        uid = (id_field.value or "").strip()
        if not uid:
            id_field.error_text = "Required"
            id_field.update()
            return
        utype = type_dropdown.value or "Valve"
        if current_graph is None:
            edit = {
                "action": "add_unit",
                "unit": {"id": uid, "type": utype, "controllable": controllable_check.value, "params": {}},
            }
            base = {"environment_type": "thermodynamic", "units": [], "connections": []}
            updated = apply_graph_edit(base, edit)
            new_graph = dict_to_graph(updated)
        else:
            edit = {
                "action": "add_unit",
                "unit": {"id": uid, "type": utype, "controllable": controllable_check.value, "params": {}},
            }
            try:
                updated = apply_graph_edit(graph_to_dict(current_graph), edit)
                new_graph = dict_to_graph(updated)
            except ValueError as err:
                id_field.error_text = str(err)
                id_field.update()
                return
        _close_dlg()
        on_saved(new_graph)

    def _close_dlg() -> None:
        dlg.open = False
        page.update()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Add node"),
        content=ft.Container(
            content=ft.Column(
                [id_field, type_dropdown, controllable_check],
                tight=True,
                width=280,
            ),
        ),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: _close_dlg()),
            ft.TextButton("Save", on_click=save),
        ],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
