"""Shared Flet GUI utilities (notifications, gestures, file picker, etc.)."""

from gui.components.progress_overlay import build_progress_overlay
from gui.utils.file_picker import register_file_picker
from gui.utils.ids import new_id
from gui.utils.role_settings_discovery import (
    RoleLlmUiEntry,
    discover_role_llm_ui_entries,
)
from gui.utils.time import now_ts
from gui.utils.ui_utils import _toast, safe_page_update, safe_update

__all__ = [
    "RoleLlmUiEntry",
    "_toast",
    "build_progress_overlay",
    "discover_role_llm_ui_entries",
    "new_id",
    "now_ts",
    "register_file_picker",
    "safe_page_update",
    "safe_update",
]
