"""
Dialog to remove a link (connection) from the process graph.
"""
from __future__ import annotations

from typing import Callable

import flet as ft

from schemas.process_graph import ProcessGraph

from gui.flet.components.workflow.dialogs.dialog_common import dict_to_graph, graph_to_dict


def open_remove_link_dialog(
    page: ft.Page,
    graph: ProcessGraph,
    on_saved: Callable[[ProcessGraph], None],
    *,
    suggested_link: tuple[str, str] | None = None,
) -> None:
    """Open dialog to remove a connection (link). If suggested_link is set (e.g. from right-click on that link), show it first."""
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

    connection_tuples = [(c.from_id, c.to_id) for c in graph.connections]
    only_suggested = suggested_link and suggested_link in connection_tuples

    if only_suggested:
        # Right-click on link: show only this link with Remove
        from_id, to_id = suggested_link[0], suggested_link[1]
        content = ft.Column(
            [
                ft.Text(f"{from_id} → {to_id}", size=14, weight=ft.FontWeight.W_500),
                ft.Row(
                    [
                        ft.TextButton("Remove", on_click=lambda e: remove_connection(from_id, to_id)),
                        ft.TextButton("Cancel", on_click=lambda e: _close_dlg()),
                    ],
                    spacing=8,
                ),
            ],
            tight=True,
            width=280,
            spacing=12,
        )
    else:
        # Toolbar or no suggestion: list all links
        rows = []
        for from_id, to_id in connection_tuples:
            rows.append(
                ft.Row(
                    [
                        ft.Text(f"{from_id} → {to_id}", size=13, expand=True),
                        ft.TextButton("Remove", on_click=lambda e, f=from_id, t=to_id: remove_connection(f, t)),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
            )
        content = ft.Container(
            content=ft.Column(
                [ft.Text("Select a link to remove:", size=12, color=ft.Colors.GREY_500)] + rows,
                tight=True,
                width=320,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Remove link"),
        content=content,
        actions=[] if only_suggested else [ft.TextButton("Close", on_click=lambda e: _close_dlg())],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
