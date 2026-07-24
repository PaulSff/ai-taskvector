"""Shared Flet GUI utilities (notifications, gestures, file picker, etc.)."""

from gui.utils.file_picker import register_file_picker
from gui.utils.role_settings_discovery import RoleLlmUiEntry, discover_role_llm_ui_entries
from .logging import setup_colored_logging
from gui.components.progress_overlay import build_progress_overlay
from gui.utils.ui_utils import safe_update, safe_page_update, _toast
from gui.utils.ids import _new_id
from gui.utils.time import _now_ts

__all__ = [
    "RoleLlmUiEntry",
    "discover_role_llm_ui_entries",
    "register_file_picker",
    "setup_colored_logging",
    "build_progress_overlay",
    "safe_update",
    "safe_page_update",
    "_toast",
    "_new_id",
    "_now_ts",
]
