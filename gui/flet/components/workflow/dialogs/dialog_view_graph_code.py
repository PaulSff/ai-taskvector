"""
Dialog to view/edit the process graph as JSON in a code editor.
"""
from __future__ import annotations

import json
from typing import Callable

import flet as ft

from core.schemas.process_graph import CodeBlock, Comment, Connection, ProcessGraph, Unit

from gui.flet.components.workflow.dialogs.dialog_common import dict_to_graph
from gui.flet.tools.code_editor import build_code_editor
from gui.flet.tools.keyboard_commands import create_keyboard_handler
from gui.flet.tools.notifications import show_toast


def open_view_graph_code_dialog(
    page: ft.Page,
    graph: ProcessGraph | None,
    *,
    unit_id: str | None = None,
    comment_id: str | None = None,
    on_graph_saved: Callable[[ProcessGraph], None] | None = None,
) -> None:
    """Open a modal dialog showing graph as JSON. If unit_id is set, show only that node and its connections.
    If comment_id is set, show only that comment. on_graph_saved: called when Apply or Delete is used."""
    try:
        if graph is None:
            json_str = "{}"
        elif comment_id is not None:
            comment = next((c for c in (graph.comments or []) if c.id == comment_id), None)
            if comment is None:
                json_str = f'{{"error": "Comment {json.dumps(comment_id)} not found"}}'
            else:
                json_str = json.dumps(comment.model_dump(), indent=2)
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
                # Include code_blocks for this unit (e.g. function/script node source) so code is visible/editable
                code_blocks_for_unit = [
                    b.model_dump(by_alias=True)
                    for b in graph.code_blocks
                    if b.id == unit_id
                ]
                filtered = {
                    "unit": unit.model_dump(by_alias=True),
                    "connections": connections,
                }
                if code_blocks_for_unit:
                    filtered["code_blocks"] = code_blocks_for_unit
                json_str = json.dumps(filtered, indent=2)
        else:
            json_str = json.dumps(
                graph.model_dump(by_alias=True), indent=2
            )
    except Exception as ex:
        json_str = f'{{"error": {json.dumps(str(ex))}}}'


    # Width of the scrollable/editable area where the code is displayed
    editor_width = 560
    code_editor_control, get_value, show_find_bar, hide_find_bar = build_code_editor(
        code=json_str, height=400, width=editor_width, page=page
    )
    title = ft.Text(
        "Comment (code)" if comment_id else ("Node (code)" if unit_id else "Graph (code)")
    )

    _prev_keyboard = getattr(page, "on_keyboard_event", None)
    page.on_keyboard_event = create_keyboard_handler(
        _prev_keyboard,
        on_find=show_find_bar,
        on_escape=hide_find_bar,
    )

    def _close_dlg() -> None:
        dlg.open = False
        page.on_keyboard_event = _prev_keyboard
        page.update()

    def apply_click(_e: ft.ControlEvent) -> None:
        if on_graph_saved is None or graph is None:
            return
        try:
            text = get_value()
            data = json.loads(text)
            if comment_id is not None:
                if isinstance(data, dict) and "error" in data:
                    page.snack_bar = ft.SnackBar(content=ft.Text("Cannot apply error payload"), open=True)
                    page.update()
                    return
                updated_comment = Comment.model_validate(data)
                new_comments = [c for c in (graph.comments or []) if c.id != comment_id] + [updated_comment]
                new_graph = graph.model_copy(update={"comments": new_comments})
                on_graph_saved(new_graph)
                _close_dlg()
                return
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
                # Merge code_blocks: keep blocks for other units; replace blocks for this unit with payload
                blocks_payload = data.get("code_blocks", [])
                other_blocks = [b for b in graph.code_blocks if b.id != unit_id]
                updated_blocks = [CodeBlock.model_validate(b) for b in blocks_payload] if isinstance(blocks_payload, list) else []
                new_code_blocks = other_blocks + updated_blocks
                new_graph = ProcessGraph(
                    environment_type=graph.environment_type,
                    units=new_units,
                    connections=new_connections,
                    code_blocks=new_code_blocks,
                    layout=graph.layout,
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
        if on_graph_saved is None or graph is None:
            return
        if comment_id is not None:
            new_comments = [c for c in (graph.comments or []) if c.id != comment_id]
            new_graph = graph.model_copy(update={"comments": new_comments or None})
            on_graph_saved(new_graph)
            _close_dlg()
            return
        if unit_id is None:
            return
        new_units = [u for u in graph.units if u.id != unit_id]
        new_connections = [
            c for c in graph.connections
            if c.from_id != unit_id and c.to_id != unit_id
        ]
        new_code_blocks = [b for b in graph.code_blocks if b.id != unit_id]
        new_layout = {k: v for k, v in (graph.layout or {}).items() if k != unit_id} or None
        new_graph = ProcessGraph(
            environment_type=graph.environment_type,
            units=new_units,
            connections=new_connections,
            code_blocks=new_code_blocks,
            layout=new_layout,
        )
        on_graph_saved(new_graph)
        _close_dlg()

    left_buttons: list[ft.Control] = []
    if on_graph_saved is not None and graph is not None:
        left_buttons.append(ft.TextButton("Apply", on_click=apply_click))
    if (unit_id is not None or comment_id is not None) and on_graph_saved is not None and graph is not None:
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
                        bgcolor="#12161A",
                        padding=8,
                    ),
                    ft.Text(
                        "Comment JSON" if comment_id else ("Node/connections JSON" if unit_id else "Graph JSON (units, connections, code_blocks, layout)"),
                        size=12,
                        color=ft.Colors.GREY_400,
                    ),
                    code_editor_control,
                ],
                spacing=8,
            ),
            width=editor_width,
            bgcolor="#12161A",
        ),
        actions=[ft.TextButton("Close", on_click=lambda e: _close_dlg())],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
