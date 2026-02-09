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

# LLM (Ollama) settings for assistants chat
KEY_OLLAMA_HOST = "ollama_host"
KEY_OLLAMA_MODEL = "ollama_model"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"

# Chat history persistence (assistants chat)
KEY_CHAT_HISTORY_DIR = "chat_history_dir"
DEFAULT_CHAT_HISTORY_DIR = "chat_history"


def _resolve_dir(value: str) -> Path:
    """
    Resolve a directory path from settings.
    - If absolute: use as-is
    - If relative: interpret relative to repo root
    """
    p = Path((value or "").strip()).expanduser()
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p


def _default_chat_history_dir() -> str:
    return DEFAULT_CHAT_HISTORY_DIR


def _default_project_name() -> str:
    return DEFAULT_PROJECT_NAME


def _default_workflow_save_path_template() -> str:
    return DEFAULT_WORKFLOW_SAVE_PATH_TEMPLATE


def load_settings() -> dict:
    """Load settings from config/app_settings.json. Creates config dir and default file if missing."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "config" / "my_workflows").mkdir(parents=True, exist_ok=True)
    _resolve_dir(_default_chat_history_dir()).mkdir(parents=True, exist_ok=True)
    if not SETTINGS_PATH.exists():
        default = {
            KEY_WORKFLOW_PROJECT_NAME: _default_project_name(),
            KEY_WORKFLOW_SAVE_PATH_TEMPLATE: _default_workflow_save_path_template(),
            KEY_OLLAMA_HOST: DEFAULT_OLLAMA_HOST,
            KEY_OLLAMA_MODEL: DEFAULT_OLLAMA_MODEL,
            KEY_CHAT_HISTORY_DIR: _default_chat_history_dir(),
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
        if KEY_OLLAMA_HOST not in data:
            data[KEY_OLLAMA_HOST] = DEFAULT_OLLAMA_HOST
        if KEY_OLLAMA_MODEL not in data:
            data[KEY_OLLAMA_MODEL] = DEFAULT_OLLAMA_MODEL
        if KEY_CHAT_HISTORY_DIR not in data:
            data[KEY_CHAT_HISTORY_DIR] = _default_chat_history_dir()
        return data
    except (json.JSONDecodeError, OSError):
        return {
            KEY_WORKFLOW_PROJECT_NAME: _default_project_name(),
            KEY_WORKFLOW_SAVE_PATH_TEMPLATE: _default_workflow_save_path_template(),
        }


def save_settings(
    *,
    workflow_project_name: str | None = None,
    workflow_save_path_template: str | None = None,
    ollama_host: str | None = None,
    ollama_model: str | None = None,
    chat_history_dir: str | None = None,
) -> None:
    """Write settings to config/app_settings.json (only provided fields are updated)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = load_settings()
    if workflow_project_name is not None:
        data[KEY_WORKFLOW_PROJECT_NAME] = (workflow_project_name or "").strip() or _default_project_name()
    if workflow_save_path_template is not None:
        data[KEY_WORKFLOW_SAVE_PATH_TEMPLATE] = (
            (workflow_save_path_template or "").strip() or _default_workflow_save_path_template()
        )
    if ollama_host is not None:
        data[KEY_OLLAMA_HOST] = (ollama_host or "").strip() or DEFAULT_OLLAMA_HOST
    if ollama_model is not None:
        data[KEY_OLLAMA_MODEL] = (ollama_model or "").strip() or DEFAULT_OLLAMA_MODEL
    if chat_history_dir is not None:
        data[KEY_CHAT_HISTORY_DIR] = (chat_history_dir or "").strip() or _default_chat_history_dir()
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Ensure dirs exist (best effort)
    try:
        _resolve_dir(str(data.get(KEY_CHAT_HISTORY_DIR) or _default_chat_history_dir())).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def get_workflow_project_name() -> str:
    """Return the stored workflow project name (default if not set)."""
    return load_settings().get(KEY_WORKFLOW_PROJECT_NAME) or _default_project_name()


def get_workflow_save_path_template() -> str:
    """Return the stored workflow save path template (default if not set)."""
    return load_settings().get(KEY_WORKFLOW_SAVE_PATH_TEMPLATE) or _default_workflow_save_path_template()


def get_ollama_host() -> str:
    """Return Ollama host URL, e.g. http://127.0.0.1:11434"""
    return load_settings().get(KEY_OLLAMA_HOST) or DEFAULT_OLLAMA_HOST


def get_ollama_model() -> str:
    """Return Ollama model name to use for assistants chat."""
    return load_settings().get(KEY_OLLAMA_MODEL) or DEFAULT_OLLAMA_MODEL


def get_chat_history_dir() -> Path:
    """Return resolved directory path where chat histories are stored."""
    raw = load_settings().get(KEY_CHAT_HISTORY_DIR) or _default_chat_history_dir()
    return _resolve_dir(str(raw))


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
    ollama_host_value = initial.get(KEY_OLLAMA_HOST) or DEFAULT_OLLAMA_HOST
    ollama_model_value = initial.get(KEY_OLLAMA_MODEL) or DEFAULT_OLLAMA_MODEL
    chat_history_dir_value = initial.get(KEY_CHAT_HISTORY_DIR) or _default_chat_history_dir()

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
    ollama_host_field = ft.TextField(
        label="Ollama server (host:port)",
        value=ollama_host_value,
        hint_text="e.g. http://127.0.0.1:11434",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    ollama_model_field = ft.TextField(
        label="Ollama model",
        value=ollama_model_value,
        hint_text="e.g. llama3.2",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    chat_history_dir_field = ft.TextField(
        label="Chat history directory",
        value=chat_history_dir_value,
        hint_text="e.g. chat_history (relative to repo) or /abs/path/chat_history",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )

    def save_click(_e: ft.ControlEvent) -> None:
        new_project = (project_field.value or "").strip() or _default_project_name()
        new_template = (template_field.value or "").strip() or _default_workflow_save_path_template()
        new_host = (ollama_host_field.value or "").strip() or DEFAULT_OLLAMA_HOST
        new_model = (ollama_model_field.value or "").strip() or DEFAULT_OLLAMA_MODEL
        new_chat_dir = (chat_history_dir_field.value or "").strip() or _default_chat_history_dir()
        try:
            save_settings(
                workflow_project_name=new_project,
                workflow_save_path_template=new_template,
                ollama_host=new_host,
                ollama_model=new_model,
                chat_history_dir=new_chat_dir,
            )
            project_field.value = new_project
            template_field.value = new_template
            ollama_host_field.value = new_host
            ollama_model_field.value = new_model
            chat_history_dir_field.value = new_chat_dir
            project_field.update()
            template_field.update()
            ollama_host_field.update()
            ollama_model_field.update()
            chat_history_dir_field.update()
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
                ft.Text("Assistants / LLM", size=14, weight=ft.FontWeight.W_600),
                ollama_host_field,
                ft.Container(height=8),
                ollama_model_field,
                ft.Container(height=8),
                chat_history_dir_field,
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
