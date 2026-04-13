"""Shared Flet GUI utilities (notifications, gestures, file picker, etc.)."""

from gui.utils.file_picker import register_file_picker
from gui.utils.role_settings_discovery import RoleLlmUiEntry, discover_role_llm_ui_entries

__all__ = [
    "RoleLlmUiEntry",
    "discover_role_llm_ui_entries",
    "register_file_picker",
]
