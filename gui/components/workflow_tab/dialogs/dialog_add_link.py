from __future__ import annotations

from typing import Callable, cast

import flet as ft
from flet import Control, Event

from core.schemas.process_graph import ProcessGraph


def _port_options_for_unit(
    unit_id: str,
    graph: ProcessGraph,
    as_output: bool,
) -> list[tuple[str, str]]:
    units_by_id = {u.id: u for u in graph.units}
    unit = units_by_id.get(unit_id)
    if not unit:
        return [("0", "0")]
    ports = unit.output_ports if as_output else unit.input_ports
    if not ports:
        return [("0", "0")]
    return [(str(i), f"{i}: {p.name}") for i, p in enumerate(ports)]


def open_add_link_dialog(
    page: ft.Page,
    graph: ProcessGraph,
    on_saved: Callable[[ProcessGraph], None],
) -> None:
    from gui.components.workflow_tab.workflows.edit_workflows.runner import (
        apply_edit_via_workflow,
    )
    from gui.components.settings import (
        get_workflow_project_name,
        get_workflow_save_path_template,
    )
    from gui.utils import save_workflow_version
    from gui.utils.notifications import show_toast

    unit_ids = [u.id for u in graph.units]
    if len(unit_ids) < 2:
        msg_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Add link"),
            content=ft.Text("Need at least two nodes to create a link."),
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

    def _toast(msg: str) -> None:
        async def _run() -> None:
            await show_toast(page, msg)

        page.run_task(_run)

    async def _add_and_autosave(from_id: str, to_id: str, from_port: str, to_port: str) -> None:
        edit = {
            "action": "connect",
            "from": from_id,
            "to": to_id,
            "from_port": from_port,
            "to_port": to_port,
        }
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

    from_id_init = unit_ids[0]
    to_id_init = unit_ids[1] if len(unit_ids) > 1 else unit_ids[0]
    from_port_opts = _port_options_for_unit(from_id_init, graph, as_output=True)
    to_port_opts = _port_options_for_unit(to_id_init, graph, as_output=False)

    from_dropdown = ft.Dropdown(
        label="From",
        options=[ft.dropdown.Option(uid) for uid in unit_ids],
        value=from_id_init,
    )
    from_port_dropdown = ft.Dropdown(
        label="From port",
        options=[ft.dropdown.Option(v, text=label) for v, label in from_port_opts],
        value=from_port_opts[0][0] if from_port_opts else "0",
    )
    to_dropdown = ft.Dropdown(
        label="To",
        options=[ft.dropdown.Option(uid) for uid in unit_ids],
        value=to_id_init,
    )
    to_port_dropdown = ft.Dropdown(
        label="To port",
        options=[ft.dropdown.Option(v, text=label) for v, label in to_port_opts],
        value=to_port_opts[0][0] if to_port_opts else "0",
    )
    error_text = ft.Text("", color=ft.Colors.ERROR, size=12)

    def _refresh_from_port(e: ft.ControlEvent | None = None) -> None:
        uid = from_dropdown.value
        if not uid:
            return
        opts = _port_options_for_unit(uid, graph, as_output=True)
        from_port_dropdown.options = [
            ft.dropdown.Option(v, text=label) for v, label in opts
        ]
        from_port_dropdown.value = opts[0][0] if opts else "0"
        from_port_dropdown.update()

    def _refresh_to_port(e: ft.ControlEvent | None = None) -> None:
        uid = to_dropdown.value
        if not uid:
            return
        opts = _port_options_for_unit(uid, graph, as_output=False)
        to_port_dropdown.options = [
            ft.dropdown.Option(v, text=label) for v, label in opts
        ]
        to_port_dropdown.value = opts[0][0] if opts else "0"
        to_port_dropdown.update()

    try:
        from_dropdown.on_change.append(_refresh_from_port)  # type: ignore[attr-defined]
    except Exception:
        setattr(from_dropdown, "on_change", _refresh_from_port)  # type: ignore[attr-defined]

    try:
        to_dropdown.on_change.append(_refresh_to_port)  # type: ignore[attr-defined]
    except Exception:
        setattr(to_dropdown, "on_change", _refresh_to_port)  # type: ignore[attr-defined]

    async def _save_impl() -> None:
        from_id = from_dropdown.value
        to_id = to_dropdown.value
        from_port = str(from_port_dropdown.value or "0")
        to_port = str(to_port_dropdown.value or "0")

        if not from_id or not to_id:
            error_text.value = "Select From and To"
            error_text.update()
            return
        if from_id == to_id:
            error_text.value = "From and To must be different"
            error_text.update()
            return

        existing = any(
            c.from_id == from_id
            and c.to_id == to_id
            and str(c.from_port or "0") == from_port
            and str(c.to_port or "0") == to_port
            for c in graph.connections
        )
        if existing:
            error_text.value = "Link already exists"
            error_text.update()
            return

        await _add_and_autosave(from_id, to_id, from_port, to_port)
        _close_dlg()

    def _on_save(e: ft.ControlEvent) -> None:
        page.run_task(_save_impl)


    def _on_cancel(e: ft.Event[ft.TextButton] | None = None) -> None:
        _close_dlg()

    btn_cancel = cast(
        Control,
        ft.TextButton(
            "Cancel",
            on_click=cast("Callable[[Event[ft.TextButton]], None]", _on_cancel),
        ),
    )
    btn_save = cast(
        Control,
        ft.TextButton(
            "Save",
            on_click=cast("Callable[[Event[ft.TextButton]], None]", _on_save),
        ),
    )

    actions_row = ft.Row(
        controls=[btn_cancel, btn_save],
        alignment=ft.MainAxisAlignment.END,
        spacing=8,
    )

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Add link"),
        content=ft.Container(
            content=ft.Column(
                [
                    from_dropdown,
                    from_port_dropdown,
                    to_dropdown,
                    to_port_dropdown,
                    error_text,
                ],
                tight=True,
                width=280,
            ),
        ),
        actions=[actions_row],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
