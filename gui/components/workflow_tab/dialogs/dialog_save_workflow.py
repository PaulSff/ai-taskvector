"""
Dialog to save the current workflow graph as a *versioned* JSON file.

Path is defined by a template stored in Settings, with placeholders:
  - $PROJECT_NAME$
  - $YY-MM-DD-HHMMSS$

Each save writes a new timestamped file *only if the graph changed* compared to the latest saved version.
Change detection uses an MD5 hash of the canonical JSON.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Union, cast

import flet as ft

from core.schemas.process_graph import ProcessGraph
from gui.components.settings import (
    get_workflow_project_name,
    get_workflow_save_path_template,
    save_settings,
)
from gui.utils.notifications import show_toast
from gui.utils.save_workflow import (
    _now_timestamp,
    resolve_workflow_save_path,
    save_workflow_version,
)


def open_save_workflow_dialog(
    page: ft.Page,
    graph_or_ref: Optional[
        Union[ProcessGraph, dict, list[Optional[Union[ProcessGraph, dict]]]]
    ],
    *,
    on_saved: Optional[Callable[[Path], None]] = None,
) -> None:
    """
    Open a modal dialog to save the current graph as a new versioned JSON file.
    graph_or_ref: the current graph (ProcessGraph | dict | None), or a single-element list (graph_ref)
                  so that the Save button uses the latest graph at click time, not at dialog open.
    """

    def _get_graph() -> Optional[Union[ProcessGraph, dict]]:
        # If caller passed a single-element list as a reference, return its first element (which may be None).
        if isinstance(graph_or_ref, list) and len(graph_or_ref) > 0:
            return graph_or_ref[0]
        return graph_or_ref  # type: ignore[return-value]

    initial_project = get_workflow_project_name()
    # Template is configured in Settings; Save dialog only needs project name.
    template_from_settings = get_workflow_save_path_template()

    project_tf = ft.TextField(
        label="Project name",
        value=initial_project,
        width=340,
        autofocus=True,
    )
    preview_txt = ft.Text(value="", selectable=True)

    def _update_preview() -> None:
        proj = (project_tf.value or "").strip() or "my_project"
        ts = _now_timestamp()
        resolved = (
            resolve_workflow_save_path(
                template_from_settings, project_name=proj, timestamp=ts
            )
            if template_from_settings
            else ""
        )
        preview_txt.value = f"Preview: {resolved}"
        # Guard: initial call can happen before controls are mounted on page
        try:
            preview_txt.update()
        except RuntimeError:
            pass

    project_tf.on_change = lambda _e: _update_preview()

    def _close() -> None:
        dlg.open = False
        page.update()

    def _toast(msg: str) -> None:
        async def _run() -> None:
            await show_toast(page, msg)

        page.run_task(_run)

    def _save_click(e: ft.Event[ft.Button]) -> None:
        proj = (project_tf.value or "").strip() or "my_project"
        try:
            save_settings(
                workflow_project_name=proj,
                workflow_save_path_template=template_from_settings,
            )
        except OSError:
            pass
        result = save_workflow_version(
            _get_graph(), project_name=proj, template=template_from_settings
        )
        if result.reason == "saved" and result.path is not None:
            _toast("Saved!")
            if on_saved:
                on_saved(result.path)
            _close()
            return
        if result.reason == "no_changes":
            _toast("No changes to save")
            return
        if result.reason == "no_graph":
            _toast("No workflow loaded")
            return
        _toast("Save failed")

    _update_preview()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Save workflow as"),
        content=ft.Container(
            content=ft.Column(
                controls=cast(
                    list[ft.Control],
                    [
                        ft.Text(
                            "Saves a new timestamped JSON file only if the workflow changed (MD5 vs latest).",
                            size=12,
                            color=ft.Colors.GREY_500,
                        ),
                        ft.Text(
                            "The save path template is configured in Settings.",
                            size=12,
                            color=ft.Colors.GREY_500,
                        ),
                        ft.Container(height=10),
                        project_tf,
                        ft.Container(height=8),
                        preview_txt,
                        ft.Container(height=8),
                        ft.Row(
                            controls=cast(
                                list[ft.Control],
                                [
                                    ft.Button("Save", on_click=_save_click),
                                    ft.TextButton(
                                        "Cancel", on_click=lambda e: _close()
                                    ),
                                ],
                            ),
                            spacing=8,
                        ),
                    ],
                ),
                tight=True,
                spacing=6,
            ),
            width=560,
        ),
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
