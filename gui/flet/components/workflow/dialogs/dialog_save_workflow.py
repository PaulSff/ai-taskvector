"""
Dialog to save the current workflow graph as a *versioned* JSON file.

Path is defined by a template stored in Settings, with placeholders:
  - $PROJECT_NAME$
  - $YY-MM-DD-HHMMSS$

Each save writes a new timestamped file *only if the graph changed* compared to the latest saved version.
Change detection uses an MD5 hash of the canonical JSON.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import flet as ft

from schemas.process_graph import ProcessGraph

from gui.flet.components.settings import (
    REPO_ROOT,
    get_workflow_project_name,
    get_workflow_save_path_template,
    save_settings,
)
from gui.flet.tools.notifications import show_toast


PLACEHOLDER_PROJECT_NAME = "$PROJECT_NAME$"
PLACEHOLDER_TIMESTAMP = "$YY-MM-DD-HHMMSS$"


def _now_timestamp() -> str:
    """Timestamp in YY-MM-DD-HHMMSS format."""
    return datetime.now().strftime("%y-%m-%d-%H%M%S")


def resolve_workflow_save_path(template: str, *, project_name: str, timestamp: str) -> str:
    """Apply placeholder substitution and return the resolved path string."""
    return (
        (template or "")
        .replace(PLACEHOLDER_PROJECT_NAME, project_name)
        .replace(PLACEHOLDER_TIMESTAMP, timestamp)
    )


def _graph_json_bytes(graph: ProcessGraph) -> bytes:
    """
    Stable bytes for hashing/saving.
    sort_keys=True reduces spurious diffs due to dict key order.
    """
    payload = graph.model_dump(by_alias=True)
    s = json.dumps(payload, indent=2, sort_keys=True)
    return s.encode("utf-8")


def _md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _latest_saved_json(project_dir: Path) -> Path | None:
    """Return the lexicographically-latest JSON file in project_dir, or None."""
    if not project_dir.exists() or not project_dir.is_dir():
        return None
    files = sorted([p for p in project_dir.glob("*.json") if p.is_file()])
    return files[-1] if files else None


@dataclass(frozen=True)
class SaveResult:
    saved: bool
    path: Path | None
    reason: str  # "saved" | "no_changes" | "no_graph" | "error"


def save_workflow_version(
    graph: ProcessGraph | None,
    *,
    project_name: str | None = None,
    template: str | None = None,
) -> SaveResult:
    """
    Save a new timestamped workflow JSON version (if graph differs from latest).
    Returns SaveResult with status and saved path (if saved).
    """
    if graph is None:
        return SaveResult(saved=False, path=None, reason="no_graph")

    project_name = (project_name or get_workflow_project_name()).strip() or "my_project"
    template = (template or get_workflow_save_path_template()).strip()
    if not template:
        return SaveResult(saved=False, path=None, reason="error")

    ts = _now_timestamp()
    rel = resolve_workflow_save_path(template, project_name=project_name, timestamp=ts).strip()
    path = (REPO_ROOT / rel) if not Path(rel).is_absolute() else Path(rel)
    project_dir = path.parent

    try:
        data = _graph_json_bytes(graph)
        cur_hash = _md5_hex(data)

        latest = _latest_saved_json(project_dir)
        if latest is not None:
            latest_bytes = latest.read_bytes()
            if _md5_hex(latest_bytes) == cur_hash:
                return SaveResult(saved=False, path=latest, reason="no_changes")

        project_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return SaveResult(saved=True, path=path, reason="saved")
    except OSError:
        return SaveResult(saved=False, path=path, reason="error")


def open_save_workflow_dialog(
    page: ft.Page,
    graph: ProcessGraph | None,
    *,
    on_saved: Callable[[Path], None] | None = None,
) -> None:
    """Open a modal dialog to save the current graph as a new versioned JSON file."""
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
            resolve_workflow_save_path(template_from_settings, project_name=proj, timestamp=ts)
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

    def _save_click(_e: ft.ControlEvent) -> None:
        proj = (project_tf.value or "").strip() or "my_project"

        # Persist project name so next save uses the same value (template is owned by Settings)
        try:
            save_settings(workflow_project_name=proj, workflow_save_path_template=template_from_settings)
        except OSError:
            pass

        result = save_workflow_version(graph, project_name=proj, template=template_from_settings)
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
        title=ft.Text("Save workflow"),
        content=ft.Container(
            content=ft.Column(
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
                        [
                            ft.ElevatedButton("Save", on_click=_save_click),
                            ft.TextButton("Cancel", on_click=lambda e: _close()),
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

