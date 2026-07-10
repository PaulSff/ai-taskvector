"""
Dialog to remove a link (connection) from the process graph.
"""

from __future__ import annotations

from typing import Callable, cast

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
    """Open dialog to remove a connection (link). If suggested_link is set, show it first."""
    from gui.components.workflow_tab.workflows.edit_workflows.runner import apply_edit_via_workflow
    from gui.utils import save_workflow_version
    from gui.components.settings import get_workflow_project_name, get_workflow_save_path_template
    from gui.utils.notifications import show_toast

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

    def _close_dlg(d: ft.AlertDialog) -> None:
        d.open = False
        page.update()

    def _toast(msg: str) -> None:
        async def _run() -> None:
            await show_toast(page, msg)

        page.run_task(_run)

    async def _remove_and_autosave(
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
        on_saved(new_graph)

        proj = get_workflow_project_name()
        template = get_workflow_save_path_template()
        result = save_workflow_version(new_graph, project_name=proj, template=template)

        if result.reason == "saved":
            _toast("Saved!")
        elif result.reason == "no_changes":
            _toast("No changes to save")
        elif result.reason == "no_graph":
            _toast("No workflow loaded")
        else:
            _toast("Save failed")

    def _conn_key(c: object) -> EdgeTuple:
        fid_obj = getattr(c, "from_id", None) or (c.get("from") if isinstance(c, dict) else None)
        tid_obj = getattr(c, "to_id", None) or (c.get("to") if isinstance(c, dict) else None)
        fid = str(fid_obj) if fid_obj is not None else ""
        tid = str(tid_obj) if tid_obj is not None else ""

        fp_obj = getattr(c, "from_port", None) or (c.get("from_port") if isinstance(c, dict) else None)
        tp_obj = getattr(c, "to_port", None) or (c.get("to_port") if isinstance(c, dict) else None)
        fp = str(fp_obj) if fp_obj is not None else "0"
        tp = str(tp_obj) if tp_obj is not None else "0"

        return (fid, tid, fp, tp)

    connection_tuples: list[EdgeTuple] = [_conn_key(c) for c in graph.connections]

    link_4: EdgeTuple | None = None
    link_2: tuple[str, str] | None = None

    if suggested_link:
        if len(suggested_link) >= 4:
            link_4 = (
                str(suggested_link[0]),
                str(suggested_link[1]),
                str(suggested_link[2]),
                str(suggested_link[3]),
            )
            link_2 = (str(suggested_link[0]), str(suggested_link[1]))
        elif len(suggested_link) >= 2:
            link_2 = (str(suggested_link[0]), str(suggested_link[1]))

    only_suggested = bool(link_4 and link_4 in connection_tuples)
    if not only_suggested and link_2:
        matches = [k for k in connection_tuples if k[0] == link_2[0] and k[1] == link_2[1]]
        only_suggested = len(matches) == 1 and bool(suggested_link)

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Remove link"),
        content=ft.Text(""),
        actions=[],
    )

    if only_suggested:
        assert link_2 is not None
        if link_4:
            from_id, to_id = link_4[0], link_4[1]
            from_port, to_port = link_4[2], link_4[3]
        else:
            from_id, to_id = link_2[0], link_2[1]
            from_port, to_port = None, None

        def on_remove(e) -> None:
            async def _task() -> None:
                await _remove_and_autosave(from_id, to_id, from_port, to_port)
                _close_dlg(dlg)

            page.run_task(_task)

        def on_cancel(e) -> None:
            _close_dlg(dlg)

        dlg.content = ft.Column(
            controls=cast(
                list[ft.Control],
                [
                    ft.Text(
                        f"{from_id} → {to_id}"
                        + (f" (ports {from_port}→{to_port})" if from_port is not None else ""),
                        size=14,
                        weight=ft.FontWeight.W_500,
                    ),
                    ft.Row(
                        controls=cast(
                            list[ft.Control],
                            [
                                ft.TextButton("Remove", on_click=on_remove),
                                ft.TextButton("Cancel", on_click=on_cancel),
                            ],
                        ),
                        spacing=8,
                    ),
                ],
            ),
            tight=True,
            width=280,
            spacing=12,
        )
        dlg.actions = []
    else:
        rows: list[ft.Control] = []

        for k in connection_tuples:
            fid, tid = k[0], k[1]
            fp, tp = (k[2], k[3]) if len(k) > 3 else ("0", "0")

            fp_display = None if fp in (None, "0", "") else fp
            tp_display = None if tp in (None, "0", "") else tp

            label = f"{fid} → {tid}" + (
                f" ({fp_display}→{tp_display})" if fp_display and tp_display else ""
            )

            def make_on_remove(f: str, t: str, fp2: str | None, tp2: str | None):
                def _on_remove(e) -> None:
                    async def _task() -> None:
                        await _remove_and_autosave(f, t, fp2, tp2)
                        _close_dlg(dlg)

                    page.run_task(_task)

                return _on_remove

            rows.append(
                ft.Row(
                    controls=cast(
                        list[ft.Control],
                        [
                            ft.Text(label, size=13, expand=True),
                            ft.TextButton(
                                "Remove",
                                on_click=make_on_remove(fid, tid, fp_display, tp_display),
                            ),
                        ],
                    ),
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
            )

        dlg.content = ft.Container(
            content=ft.Column(
                controls=cast(
                    list[ft.Control],
                    [
                        ft.Text("Select a link to remove:", size=12, color=ft.Colors.GREY_500),
                        *rows,
                    ],
                ),
                tight=True,
                width=320,
                scroll=ft.ScrollMode.AUTO,
            )
        )
        dlg.actions = [ft.TextButton("Close", on_click=lambda e: _close_dlg(dlg))]

    page.overlay.append(dlg)
    dlg.open = True
    page.update()
