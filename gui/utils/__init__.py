"""Shared Flet GUI utilities (notifications, gestures, file picker, etc.)."""

from gui.utils.file_picker import register_file_picker
from gui.utils.role_settings_discovery import RoleLlmUiEntry, discover_role_llm_ui_entries
from gui.utils.save_workflow import (
    _now_timestamp,
    resolve_workflow_save_path,
    _graph_to_payload,
    _graph_json_bytes,
    _md5_hex,
    _latest_saved_json,
    SaveResult,
    save_workflow_version,
)
from .logging import setup_colored_logging
from gui.components.progress_overlay import build_progress_overlay

__all__ = [
    "RoleLlmUiEntry",
    "discover_role_llm_ui_entries",
    "register_file_picker",
    "_now_timestamp",
    "resolve_workflow_save_path",
    "_graph_to_payload",
    "_graph_json_bytes",
    "_md5_hex",
    "_latest_saved_json",
    "SaveResult",
    "save_workflow_version",
    "setup_colored_logging",
    "build_progress_overlay",
]
