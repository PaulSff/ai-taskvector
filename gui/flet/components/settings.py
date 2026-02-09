"""
Settings tab: store app preferences (e.g. workflow save path) in config JSON.
Default workflow path template:
  config/my_workflows/$PROJECT_NAME$/$PROJECT_NAME$_workflow_$YY-MM-DD-HHMMSS$.json
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import flet as ft

# Repo root: gui/flet/components/settings.py -> ... -> repo
_COMPONENTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = _COMPONENTS_DIR.parent.parent.parent

SETTINGS_FILENAME = "app_settings.json"
CONFIG_DIR = REPO_ROOT / "config"
SETTINGS_PATH = CONFIG_DIR / SETTINGS_FILENAME

# Workflow save settings (versioned saves)
DEFAULT_WORKFLOWS_DIR = "config/my_workflows"
DEFAULT_PROJECT_NAME = "my_project"
DEFAULT_WORKFLOW_SAVE_PATH_TEMPLATE = (
    "config/my_workflows/$PROJECT_NAME$/$PROJECT_NAME$_workflow_$YY-MM-DD-HHMMSS$.json"
)

KEY_WORKFLOW_PROJECT_NAME = "workflow_project_name"
KEY_WORKFLOW_SAVE_PATH_TEMPLATE = "workflow_save_path_template"


def _default_project_name() -> str:
    return DEFAULT_PROJECT_NAME


def _default_workflow_save_path_template() -> str:
    return DEFAULT_WORKFLOW_SAVE_PATH_TEMPLATE


def load_settings() -> dict:
    """Load settings from config/app_settings.json. Creates config dir and default file if missing."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "config" / "my_workflows").mkdir(parents=True, exist_ok=True)
    if not SETTINGS_PATH.exists():
        default = {
            KEY_WORKFLOW_PROJECT_NAME: _default_project_name(),
            KEY_WORKFLOW_SAVE_PATH_TEMPLATE: _default_workflow_save_path_template(),
        }
        try:
            SETTINGS_PATH.write_text(json.dumps(default, indent=2), encoding="utf-8")
        except OSError:
            pass
        return default
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {
                KEY_WORKFLOW_PROJECT_NAME: _default_project_name(),
                KEY_WORKFLOW_SAVE_PATH_TEMPLATE: _default_workflow_save_path_template(),
            }

        # Back-compat: older setting used a single workflow_save_path; keep it but prefer template+project.
        if KEY_WORKFLOW_PROJECT_NAME not in data:
            data[KEY_WORKFLOW_PROJECT_NAME] = _default_project_name()
        if KEY_WORKFLOW_SAVE_PATH_TEMPLATE not in data:
            data[KEY_WORKFLOW_SAVE_PATH_TEMPLATE] = _default_workflow_save_path_template()
        return data
    except (json.JSONDecodeError, OSError):
        return {
            KEY_WORKFLOW_PROJECT_NAME: _default_project_name(),
            KEY_WORKFLOW_SAVE_PATH_TEMPLATE: _default_workflow_save_path_template(),
        }


def save_settings(*, workflow_project_name: str, workflow_save_path_template: str) -> None:
    """Write workflow project name and path template to config/app_settings.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = load_settings()
    data[KEY_WORKFLOW_PROJECT_NAME] = (workflow_project_name or "").strip() or _default_project_name()
    data[KEY_WORKFLOW_SAVE_PATH_TEMPLATE] = (
        (workflow_save_path_template or "").strip() or _default_workflow_save_path_template()
    )
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_workflow_project_name() -> str:
    """Return the stored workflow project name (default if not set)."""
    return load_settings().get(KEY_WORKFLOW_PROJECT_NAME) or _default_project_name()


def get_workflow_save_path_template() -> str:
    """Return the stored workflow save path template (default if not set)."""
    return load_settings().get(KEY_WORKFLOW_SAVE_PATH_TEMPLATE) or _default_workflow_save_path_template()


def build_settings_tab(
    page: ft.Page,
    *,
    on_saved: Callable[[], None] | None = None,
) -> ft.Control:
    """
    Build the Settings tab content: workflow project name + workflow save path template.
    on_saved: optional callback called when user saves.
    """
    initial = load_settings()
    project_value = initial.get(KEY_WORKFLOW_PROJECT_NAME) or _default_project_name()
    template_value = initial.get(KEY_WORKFLOW_SAVE_PATH_TEMPLATE) or _default_workflow_save_path_template()

    project_field = ft.TextField(
        label="Workflow project name",
        value=project_value,
        hint_text="e.g. temperature_control",
        width=400,
    )
    template_field = ft.TextField(
        label="Workflow save path template",
        value=template_value,
        hint_text="e.g. config/my_workflows/$PROJECT_NAME$/$PROJECT_NAME$_workflow_$YY-MM-DD-HHMMSS$.json",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )

    def save_click(_e: ft.ControlEvent) -> None:
        new_project = (project_field.value or "").strip() or _default_project_name()
        new_template = (template_field.value or "").strip() or _default_workflow_save_path_template()
        try:
            save_settings(workflow_project_name=new_project, workflow_save_path_template=new_template)
            project_field.value = new_project
            template_field.value = new_template
            project_field.update()
            template_field.update()
            if on_saved:
                on_saved()
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
                    "Workflow save settings (project name + versioned save path template). "
                    f"Stored in {SETTINGS_FILENAME} under config/.",
                    size=12,
                    color=ft.Colors.GREY_500,
                ),
                ft.Container(height=16),
                project_field,
                ft.Container(height=8),
                template_field,
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
