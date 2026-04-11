"""
Dialog to export the workflow to external runtime formats (Node-RED, PyFlow, n8n).

Exports the current graph (including oracles and RL agents) to JSON suitable for
import into Node-RED, PyFlow, or n8n. Enables roundtrip: import → edit → export → run.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import flet as ft

from core.schemas.process_graph import ProcessGraph

from gui.flet.components.settings import REPO_ROOT
from gui.flet.components.workflow.core_workflows import run_export_workflow, run_runtime_label
from gui.flet.utils.notifications import show_toast

EXPORT_FORMATS: list[tuple[str, str]] = [
    ("Node-RED", "node_red"),
    ("PyFlow", "pyflow"),
    ("n8n", "n8n"),
]


def _allowed_export_format(graph: ProcessGraph | None) -> tuple[list[tuple[str, str]], str]:
    """
    Return (allowed_options, default_value) based on graph runtime (via RuntimeLabel workflow).
    Export only to the same runtime format when origin is known.
    """
    rt, _ = run_runtime_label(graph) if graph is not None else ("canonical", True)
    if rt not in ("canonical", "dict") and rt in (f[1] for f in EXPORT_FORMATS):
        opt = next((x for x in EXPORT_FORMATS if x[1] == rt), EXPORT_FORMATS[0])
        return [opt], opt[1]
    if rt == "ryven":
        # Ryven export not implemented; PyFlow is Python runtime fallback
        pyflow_opt = next((x for x in EXPORT_FORMATS if x[1] == "pyflow"), EXPORT_FORMATS[0])
        return [pyflow_opt], "pyflow"
    # canonical, dict, or unknown: allow all
    return EXPORT_FORMATS, "node_red"


def open_export_workflow_dialog(
    page: ft.Page,
    graph: ProcessGraph | None,
    *,
    on_exported: Callable[[Path], None] | None = None,
) -> None:
    """Open a modal dialog to export the workflow to Node-RED, PyFlow, or n8n format."""
    if graph is None:
        page.snack_bar = ft.SnackBar(content=ft.Text("No workflow to export"), open=True)
        page.update()
        return

    allowed, default_fmt = _allowed_export_format(graph)
    format_dropdown = ft.Dropdown(
        label="Format",
        options=[ft.dropdown.Option(key=fmt, text=label) for label, fmt in allowed],
        value=default_fmt,
        width=180,
    )
    preview_tf = ft.TextField(
        value="",
        multiline=True,
        min_lines=12,
        max_lines=20,
        read_only=True,
        text_style=ft.TextStyle(font_family="monospace", size=11),
    )
    path_tf = ft.TextField(
        label="Save path (optional)",
        hint_text="e.g. workflows/exported_flow.json",
        width=400,
    )

    def _close() -> None:
        dlg.open = False
        page.update()

    def _update_preview() -> None:
        fmt = format_dropdown.value or "node_red"
        try:
            raw, err = run_export_workflow(graph, format=fmt)
            if err:
                preview_tf.value = f"Error: {err}"
            else:
                preview_tf.value = json.dumps(raw, indent=2)
        except Exception as ex:
            preview_tf.value = f"Error: {ex}"
        try:
            preview_tf.update()
        except RuntimeError:
            pass

    format_dropdown.on_change = lambda _e: _update_preview()

    async def _copy_click(_e: ft.ControlEvent) -> None:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            await page.clipboard.set(preview_tf.value or "")
        await show_toast(page, "Copied to clipboard")

    def _save_click(_e: ft.ControlEvent) -> None:
        path_str = (path_tf.value or "").strip()
        if not path_str:
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Enter a save path"),
                open=True,
            )
            page.update()
            return
        path = Path(path_str)
        if not path.is_absolute():
            path = REPO_ROOT / path_str
        try:
            raw, err = run_export_workflow(graph, format=format_dropdown.value or "node_red")
            if err:
                raise RuntimeError(err)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
            if on_exported:
                on_exported(path)
            _close()
            async def _t() -> None:
                await show_toast(page, f"Saved to {path}")
            page.run_task(_t)
        except Exception as ex:
            page.snack_bar = ft.SnackBar(
                content=ft.Text(str(ex)[:200]),
                open=True,
            )
            page.update()

    _update_preview()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Export workflow"),
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Export the workflow (including oracles and RL agents). Format is restricted to the import origin when known.",
                        size=12,
                        color=ft.Colors.GREY_600,
                    ),
                    ft.Container(height=8),
                    format_dropdown,
                    ft.Container(height=8),
                    ft.Container(
                        content=preview_tf,
                        bgcolor="#12161A",
                        border_radius=4,
                        padding=8,
                        height=280,
                    ),
                    ft.Container(height=8),
                    path_tf,
                    ft.Row(
                        [
                            ft.ElevatedButton("Copy", on_click=_copy_click),
                            ft.ElevatedButton("Save", on_click=_save_click),
                            ft.TextButton("Close", on_click=lambda e: _close()),
                        ],
                        spacing=8,
                    ),
                ],
                tight=True,
                spacing=6,
            ),
            width=560,
        ),
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()
