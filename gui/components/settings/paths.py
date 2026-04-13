"""Repository paths and path resolution for app settings."""
from __future__ import annotations

from pathlib import Path

from .constants import SETTINGS_FILENAME

_PKG_DIR = Path(__file__).resolve().parent
_COMPONENTS_DIR = _PKG_DIR.parent
_GUI_DIR = _COMPONENTS_DIR.parent
REPO_ROOT = _GUI_DIR.parent
CONFIG_DIR = REPO_ROOT / "config"
SETTINGS_PATH = CONFIG_DIR / SETTINGS_FILENAME
_ROLES_YAML_ROOT = REPO_ROOT / "assistants" / "roles"


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


def _resolve_workflow_path(value: str, default: str) -> Path:
    """Resolve a workflow or prompt file path from settings (relative to repo root if not absolute)."""
    raw = (value or "").strip() or default
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p
