"""
Dialog to remove a link (connection) from the process graph.
"""

from __future__ import annotations

from typing import Callable, Sequence

import flet as ft

from core.schemas.process_graph import ProcessGraph
from gui.components.workflow_tab.editor.graph_visual_editor.flow_layout import EdgeTuple


def open_remove_link_dialog(
    page: ft.Page,
    graph: ProcessGraph,
    on_saved: Callable[[ProcessGraph], None],
    *,
    suggested_link: EdgeTuple | tuple[str, str] | None = None,
) -> None:
    """Open dialog to remove a connection (link). If suggested_link is set (e.g. from right-click on that link), show it first."""
    from gui.components.workflow_tab.workflows.edit_workflows.runner import (
        apply_edit_via_workflow,
    )

    if not graph.connections:
        msg_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Remove link"),
            content=ft.Text("No links to remove."),
            actions=[
                ft.TextButton(
                    "OK",
                    on_click=lambda e: (setattr(msg_dlg, "open", False), page.update()),
                )
            ],
        )
        page.overlay.append(msg_dlg)
        msg_dlg.open = True
        page.update()
        return

    def _close_dlg() -> None:
        dlg.open = False
        page.update()

    async def remove_connection(
        from_id: str,
        to_id: str,
        from_port: str | None = None,
        to_port: str | None = None,
    ) -> None:
        edit: dict = {"action": "disconnect", "from": from_id, "to": to_id}
        if from_port is not None:
            edit["from_port"] = from_port
        if to_port is not None:
            edit["to_port"] = to_port
        new_graph = await apply_edit_via_workflow(graph, edit)
        _close_dlg()
        on_saved(new_graph)

    def _conn_key(c: object) -> EdgeTuple:
        # Extract IDs as strings (fall back to empty string if missing)
        fid_obj = getattr(c, "from_id", None) or (
            c.get("from") if isinstance(c, dict) else None
        )
        tid_obj = getattr(c, "to_id", None) or (
            c.get("to") if isinstance(c, dict) else None
        )
        fid = str(fid_obj) if fid_obj is not None else ""
        tid = str(tid_obj) if tid_obj is not None else ""
        # Ports: normalize to string "0" if missing/empty
        fp_obj = getattr(c, "from_port", None) or (
            c.get("from_port") if isinstance(c, dict) else None
        )
        tp_obj = getattr(c, "to_port", None) or (
            c.get("to_port") if isinstance(c, dict) else None
        )
        fp = str(fp_obj) if fp_obj is not None else "0"
        tp = str(tp_obj) if tp_obj is not None else "0"
        return (fid, tid, fp, tp)

    # Build normalized connection tuples: each is (from_id, to_id, from_port, to_port)
    connection_tuples: list[EdgeTuple] = [_conn_key(c) for c in graph.connections]

    # Normalize suggested_link into 2- and 4-tuple forms safely
    link_4: EdgeTuple | None
    link_2: tuple[str, str] | None

    if suggested_link:
        # If it's already EdgeTuple (4-tuple) keep as-is; if it's length 2, expand ports to "0"
        if len(suggested_link) >= 4:
            # mypy: cast to EdgeTuple
            link_4 = (
                str(suggested_link[0]),
                str(suggested_link[1]),
                str(suggested_link[2]),
                str(suggested_link[3]),
            )
            link_2 = (str(suggested_link[0]), str(suggested_link[1]))
        elif len(suggested_link) >= 2:
            link_2 = (str(suggested_link[0]), str(suggested_link[1]))
            link_4 = None
        else:
            link_2 = None
            link_4 = None
    else:
        link_2 = None
        link_4 = None

    only_suggested = bool(link_4 and link_4 in connection_tuples)
    if not only_suggested and link_2:
        # Fallback: match (from_id, to_id) only if exactly one connection matches those IDs
        matches = [
            k for k in connection_tuples if k[0] == link_2[0] and k[1] == link_2[1]
        ]
        only_suggested = len(matches) == 1 and bool(suggested_link)

    if only_suggested:
        # Right-click on link: show only this link with Remove
        if link_4:
            from_id, to_id = link_4[0], link_4[1]
            from_port, to_port = link_4[2], link_4[3]
        else:
            # link_2 is guaranteed to be not None here
            assert link_2 is not None
            from_id, to_id = link_2[0], link_2[1]
            from_port, to_port = None, None

        async def _on_remove() -> None:
            await remove_connection(from_id, to_id, from_port, to_port)

        content = ft.Column(
            [
                ft.Text(
                    f"{from_id} → {to_id}"
                    + (
                        f" (ports {from_port}→{to_port})"
                        if from_port is not None
                        else ""
                    ),
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
        rows: list[ft.Control] = []
        for k in connection_tuples:
            fid, tid = k[0], k[1]
            fp, tp = (k[2], k[3]) if len(k) > 3 else ("0", "0")
            # Treat "0" as no-port (None) for display and for remove action
            fp_display = None if fp in (None, "0", "") else fp
            tp_display = None if tp in (None, "0", "") else tp
            label = f"{fid} → {tid}" + (
                f" ({fp_display}→{tp_display})" if fp_display and tp_display else ""
            )
            rows.append(
                ft.Row(
                    [
                        ft.Text(label, size=13, expand=True),
                        ft.TextButton(
                            "Remove",
                            on_click=lambda e, f=fid, t=tid, fp=fp_display, tp=tp_display: (
                                remove_connection(f, t, fp, tp)
                            ),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
            )

        # Build controls as a Sequence[ft.Control] to satisfy Flet typing expectations
        controls: Sequence[ft.Control] = [
            ft.Text("Select a link to remove:", size=12, color=ft.Colors.GREY_500)
        ]
        controls = list(controls) + rows

        content = ft.Container(
            content=ft.Column(
                controls,
                tight=True,
                width=320,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Remove link"),
        content=content,
        actions=[]
        if only_suggested
        else [ft.TextButton("Close", on_click=lambda e: _close_dlg())],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
