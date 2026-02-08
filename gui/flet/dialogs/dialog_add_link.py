"""
Dialog to add a link (connection) between two units on the process graph.
"""
from __future__ import annotations

from typing import Callable

import flet as ft

from schemas.process_graph import ProcessGraph

from gui.flet.dialogs.dialog_common import dict_to_graph, graph_to_dict


def open_add_link_dialog(
    page: ft.Page,
    graph: ProcessGraph,
    on_saved: Callable[[ProcessGraph], None],
) -> None:
    """Open dialog to add a connection (link) between two units."""
    from assistants.graph_edits import apply_graph_edit

    unit_ids = [u.id for u in graph.units]
    if len(unit_ids) < 2:
        msg_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Add link"),
            content=ft.Text("Need at least two nodes to create a link."),
            actions=[ft.TextButton("OK", on_click=lambda e: (setattr(msg_dlg, "open", False), page.update()))],
        )
        page.overlay.append(msg_dlg)
        msg_dlg.open = True
        page.update()
        return

    from_dropdown = ft.Dropdown(
        label="From",
        options=[ft.dropdown.Option(uid) for uid in unit_ids],
        value=unit_ids[0],
    )
    to_dropdown = ft.Dropdown(
        label="To",
        options=[ft.dropdown.Option(uid) for uid in unit_ids],
        value=unit_ids[1] if len(unit_ids) > 1 else unit_ids[0],
    )
    error_text = ft.Text("", color=ft.Colors.ERROR, size=12)

    def save(_e: ft.ControlEvent) -> None:
        from_id = from_dropdown.value
        to_id = to_dropdown.value
        if not from_id or not to_id:
            error_text.value = "Select From and To"
            error_text.update()
            return
        if from_id == to_id:
            error_text.value = "From and To must be different"
            error_text.update()
            return
        existing = any(c.from_id == from_id and c.to_id == to_id for c in graph.connections)
        if existing:
            error_text.value = "Link already exists"
            error_text.update()
            return
        edit = {"action": "connect", "from_id": from_id, "to_id": to_id}
        updated = apply_graph_edit(graph_to_dict(graph), edit)
        new_graph = dict_to_graph(updated)
        _close_dlg()
        on_saved(new_graph)

    def _close_dlg() -> None:
        dlg.open = False
        page.update()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Add link"),
        content=ft.Container(
            content=ft.Column(
                [from_dropdown, to_dropdown, error_text],
                tight=True,
                width=260,
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
