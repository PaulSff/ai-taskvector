"""
Dialog to remove a link (connection) from the process graph.
"""
from __future__ import annotations

from typing import Callable

import flet as ft

from core.schemas.process_graph import ProcessGraph

from gui.flet.components.workflow.dialogs.dialog_common import dict_to_graph, graph_to_dict
from gui.flet.components.workflow.flow_layout import EdgeTuple


def open_remove_link_dialog(
    page: ft.Page,
    graph: ProcessGraph,
    on_saved: Callable[[ProcessGraph], None],
    *,
    suggested_link: EdgeTuple | tuple[str, str] | None = None,
) -> None:
    """Open dialog to remove a connection (link). If suggested_link is set (e.g. from right-click on that link), show it first."""
    from core.graph.graph_edits import apply_graph_edit

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

    def remove_connection(from_id: str, to_id: str, from_port: str | None = None, to_port: str | None = None) -> None:
        edit: dict = {"action": "disconnect", "from_id": from_id, "to_id": to_id}
        if from_port is not None:
            edit["from_port"] = from_port
        if to_port is not None:
            edit["to_port"] = to_port
        updated = apply_graph_edit(graph_to_dict(graph), edit)
        new_graph = dict_to_graph(updated)
        _close_dlg()
        on_saved(new_graph)

    def _conn_key(c: object) -> EdgeTuple:
        fid = getattr(c, "from_id", None) or (c.get("from") if isinstance(c, dict) else None)
        tid = getattr(c, "to_id", None) or (c.get("to") if isinstance(c, dict) else None)
        fp = str(getattr(c, "from_port", "0") or (c.get("from_port", "0") if isinstance(c, dict) else "0"))
        tp = str(getattr(c, "to_port", "0") or (c.get("to_port", "0") if isinstance(c, dict) else "0"))
        return (fid, tid, fp, tp)

    connection_tuples = [_conn_key(c) for c in graph.connections]
    link_4 = suggested_link if (suggested_link and len(suggested_link) >= 4) else None
    link_2 = (suggested_link[0], suggested_link[1]) if (suggested_link and len(suggested_link) >= 2) else None
    only_suggested = link_4 and link_4 in connection_tuples
    if not only_suggested and link_2:
        # Fallback: match (from_id, to_id) only if exactly one connection
        matches = [k for k in connection_tuples if k[0] == link_2[0] and k[1] == link_2[1]]
        only_suggested = len(matches) == 1 and suggested_link
    if only_suggested:
        # Right-click on link: show only this link with Remove
        if link_4:
            from_id, to_id = link_4[0], link_4[1]
            from_port, to_port = link_4[2], link_4[3]
        else:
            from_id, to_id = link_2[0], link_2[1]
            from_port, to_port = None, None
        def _on_remove() -> None:
            remove_connection(from_id, to_id, from_port, to_port)
        content = ft.Column(
            [
                ft.Text(
                    f"{from_id} → {to_id}" + (f" (ports {from_port}→{to_port})" if from_port is not None else ""),
                    size=14,
                    weight=ft.FontWeight.W_500,
                ),
                ft.Row(
                    [
                        ft.TextButton("Remove", on_click=lambda e: _on_remove()),
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
        for k in connection_tuples:
            fid, tid = k[0], k[1]
            fp, tp = (k[2], k[3]) if len(k) > 3 else (None, None)
            label = f"{fid} → {tid}" + (f" ({fp}→{tp})" if fp and tp and (fp != "0" or tp != "0") else "")
            rows.append(
                ft.Row(
                    [
                        ft.Text(label, size=13, expand=True),
                        ft.TextButton(
                            "Remove",
                            on_click=lambda e, f=fid, t=tid, fp=fp, tp=tp: remove_connection(f, t, fp, tp),
                        ),
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
