"""
Dialog to remove a link (connection) from the process graph.
"""
from __future__ import annotations

from typing import Callable

import flet as ft

from schemas.process_graph import ProcessGraph

from gui.flet.dialogs.dialog_common import dict_to_graph, graph_to_dict


def open_remove_link_dialog(
    page: ft.Page,
    graph: ProcessGraph,
    on_saved: Callable[[ProcessGraph], None],
) -> None:
    """Open dialog to remove a connection (link). Lists connections with Remove button each."""
    from assistants.graph_edits import apply_graph_edit

    if not graph.connections:
        msg_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Remove link"),
            content=ft.Text("No links to remove."),
            actions=[ft.TextButton("OK", on_click=lambda e: (setattr(msg_dlg, "open", False), page.update()))],
        )
        page.overlay.append(msg_dlg)
        msg_dlg.open = True
        page.update()
        return

    def _close_dlg() -> None:
        dlg.open = False
        page.update()

    def remove_connection(from_id: str, to_id: str) -> None:
        edit = {"action": "disconnect", "from_id": from_id, "to_id": to_id}
        updated = apply_graph_edit(graph_to_dict(graph), edit)
        new_graph = dict_to_graph(updated)
        _close_dlg()
        on_saved(new_graph)

    rows = []
    for c in graph.connections:
        from_id, to_id = c.from_id, c.to_id
        rows.append(
            ft.Row(
                [
                    ft.Text(f"{from_id} → {to_id}", size=13, expand=True),
                    ft.TextButton("Remove", on_click=lambda e, f=from_id, t=to_id: remove_connection(f, t)),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )
        )

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Remove link"),
        content=ft.Container(
            content=ft.Column(
                [ft.Text("Select a link to remove:", size=12, color=ft.Colors.GREY_500)] + rows,
                tight=True,
                width=320,
                scroll=ft.ScrollMode.AUTO,
            ),
        ),
        actions=[ft.TextButton("Close", on_click=lambda e: _close_dlg())],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
