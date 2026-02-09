"""
Settings tab: store app preferences (e.g. workflow save path) in config JSON.
Default workflow path: config/my_workflows/my_workflow_DD-MM-YY.json
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

import flet as ft

# Repo root: gui/flet/components/settings.py -> ... -> repo
_COMPONENTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = _COMPONENTS_DIR.parent.parent.parent

SETTINGS_FILENAME = "app_settings.json"
CONFIG_DIR = REPO_ROOT / "config"
SETTINGS_PATH = CONFIG_DIR / SETTINGS_FILENAME
DEFAULT_WORKFLOWS_DIR = "config/my_workflows"
DEFAULT_WORKFLOW_FILENAME_PATTERN = "my_workflow_{date}.json"


def _default_workflow_save_path() -> str:
    """Default path: config/my_workflows/my_workflow_DD-MM-YY.json"""
    date_str = datetime.now().strftime("%d-%m-%y")
    return f"{DEFAULT_WORKFLOWS_DIR}/my_workflow_{date_str}.json"


def load_settings() -> dict:
    """Load settings from config/app_settings.json. Creates config dir and default file if missing."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "config" / "my_workflows").mkdir(parents=True, exist_ok=True)
    if not SETTINGS_PATH.exists():
        default = {"workflow_save_path": _default_workflow_save_path()}
        try:
            SETTINGS_PATH.write_text(json.dumps(default, indent=2), encoding="utf-8")
        except OSError:
            pass
        return default
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "workflow_save_path" not in data:
            data["workflow_save_path"] = _default_workflow_save_path()
        return data if isinstance(data, dict) else {"workflow_save_path": _default_workflow_save_path()}
    except (json.JSONDecodeError, OSError):
        return {"workflow_save_path": _default_workflow_save_path()}


def save_settings(workflow_save_path: str) -> None:
    """Write workflow_save_path to config/app_settings.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = load_settings()
    data["workflow_save_path"] = workflow_save_path.strip() or _default_workflow_save_path()
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_workflow_save_path() -> str:
    """Return the stored workflow save path (default if not set)."""
    return load_settings().get("workflow_save_path") or _default_workflow_save_path()


def build_settings_tab(
    page: ft.Page,
    *,
    on_saved: Callable[[str], None] | None = None,
) -> ft.Control:
    """
    Build the Settings tab content: workflow save path field and Save button.
    on_saved: optional callback called with the new path when user saves.
    """
    initial = load_settings()
    path_value = initial.get("workflow_save_path") or _default_workflow_save_path()

    path_field = ft.TextField(
        label="Workflow save path",
        value=path_value,
        hint_text=f"e.g. {DEFAULT_WORKFLOWS_DIR}/my_workflow_DD-MM-YY.json",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )

    def save_click(_e: ft.ControlEvent) -> None:
        new_path = (path_field.value or "").strip() or _default_workflow_save_path()
        try:
            save_settings(new_path)
            path_field.value = new_path
            path_field.update()
            if on_saved:
                on_saved(new_path)
            page.snack_bar = ft.SnackBar(content=ft.Text("Settings saved."), open=True)
            page.update()
        except OSError as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(f"Could not save: {ex}"), open=True)
            page.update()

    return ft.Container(
        content=ft.Column(
            [
                ft.Text("Settings", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    f"Path to save the current workflow graph (JSON). Stored in {SETTINGS_FILENAME} under config/.",
                    size=12,
                    color=ft.Colors.GREY_500,
                ),
                ft.Container(height=16),
                path_field,
                ft.Container(height=8),
                ft.ElevatedButton("Save", on_click=save_click),
            ],
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.START,
            spacing=4,
        ),
        padding=24,
        expand=True,
    )
