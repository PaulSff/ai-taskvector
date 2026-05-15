"""
Dialog to leave a comment on the process graph (manual note).

Runs the add_comment edit workflow via ``apply_edit_via_workflow`` (same path as assistant add_comment).
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from core.schemas.process_graph import ProcessGraph


def open_leave_comment_dialog(
    page: ft.Page,
    graph: ProcessGraph,
    on_saved: Callable[[ProcessGraph], None],
) -> None:
    """Open modal dialog: multiline comment → ``add_comment`` edit workflow → ``on_saved``."""
    from gui.components.workflow_tab.workflows.edit_workflows.runner import (
        apply_edit_via_workflow,
    )

    comment_tf = ft.TextField(
        label="Comment",
        hint_text="Write a note on this workflow…",
        multiline=True,
        min_lines=4,
        max_lines=12,
        expand=True,
        text_style=ft.TextStyle(size=13),
    )
    error_text = ft.Text("", color=ft.Colors.ERROR, size=12)

    def _close_dlg() -> None:
        dlg.open = False
        page.update()

    # Adapt save signature to accept the specific Event type flet expects.
    def save(e: ft.Event[ft.TextButton]) -> None:
        info = (comment_tf.value or "").strip()
        if not info:
            error_text.value = "Enter comment text."
            error_text.update()
            return
        edit = {
            "action": "add_comment",
            "info": info,
            "commenter": "user",
        }
        try:
            new_graph = apply_edit_via_workflow(graph, edit)
        except Exception as ex:
            error_text.value = str(ex)[:400]
            error_text.update()
            return
        _close_dlg()
        on_saved(new_graph)

    # Use callables with the exact expected signature for on_click.
    def cancel_click(_: ft.Event[ft.TextButton]) -> None:
        _close_dlg()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Leave comment"),
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Adds a note to the graph (visible in the workflow editor).",
                        size=11,
                        color=ft.Colors.GREY_500,
                    ),
                    comment_tf,
                    error_text,
                ],
                tight=True,
                width=420,
                scroll=ft.ScrollMode.AUTO,
            ),
        ),
        actions=[
            ft.TextButton("Cancel", on_click=cancel_click),
            ft.TextButton("Add comment", on_click=save),
        ],
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
