"""Resolve main agents-chat workflow JSON paths from each role's ``role.yaml`` ``chat.workflow``."""

from __future__ import annotations

from pathlib import Path

from agents.roles.registry import (
    get_role,
)

from .registry import CHAT_NAME_CREATOR_ROLE_ID

_ROLES_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _ROLES_ROOT.parent.parent

# When ``chat.workflow`` is omitted, use the same filenames as the shipped role.yaml files.
_DEFAULT_MAIN_WORKFLOW_BY_ROLE: dict[str, str] = {
    CHAT_NAME_CREATOR_ROLE_ID: "create_filename.json",
}

def get_role_chat_workflow_path(role_id: str) -> Path:
    """
    Return the absolute path to the workflow JSON for a role's chat.

    ``RoleConfig`` stores the optional ``chat:`` block as flattened fields:

    - ``role.chat_enabled``
    - ``role.chat_workflow``

    Relative workflow paths are resolved under:

    ``agents/roles/<role_id>/``
    """
    key = (role_id or "").strip()

    if not key:
        raise ValueError("role_id is required")

    role = get_role(key)

    raw_workflow = ""

    if role.chat_enabled and role.chat_workflow is not None:
        raw_workflow = str(role.chat_workflow).strip()

    if not raw_workflow:
        raw_workflow = _DEFAULT_MAIN_WORKFLOW_BY_ROLE.get(key, "").strip()

    if not raw_workflow:
        raise ValueError(
            f"Role {key!r} has no chat.workflow in role.yaml "
            "and no built-in default filename."
        )

    workflow_path = Path(raw_workflow).expanduser()

    if workflow_path.is_absolute():
        return workflow_path.resolve()

    normalized_path = workflow_path.as_posix()

    if normalized_path.startswith(("agents/", "gui/", "config/")):
        return (_REPO_ROOT / workflow_path).resolve()

    return (_ROLES_ROOT / key / workflow_path).resolve()
