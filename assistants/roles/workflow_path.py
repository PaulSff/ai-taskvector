"""Resolve main assistants-chat workflow JSON paths from each role's ``role.yaml`` ``chat.workflow``."""
from __future__ import annotations

from pathlib import Path

from assistants.roles.registry import (
    RL_COACH_ROLE_ID,
    WORKFLOW_DESIGNER_ROLE_ID,
    get_role,
)

_ROLES_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _ROLES_ROOT.parent.parent

# When ``chat.workflow`` is omitted, use the same filenames as the shipped role.yaml files.
_DEFAULT_MAIN_WORKFLOW_BY_ROLE: dict[str, str] = {
    WORKFLOW_DESIGNER_ROLE_ID: "assistant_workflow.json",
    RL_COACH_ROLE_ID: "rl_coach_workflow.json",
}


def get_role_chat_workflow_path(role_id: str) -> Path:
    """
    Return absolute path to the workflow JSON for this role's chat.

    - ``chat.workflow`` in ``role.yaml`` is normally a filename under ``assistants/roles/<role_id>/``.
    - If it is relative but starts with ``assistants/``, ``gui/``, or ``config/``, it is resolved from the repo root.
    - If it is an absolute path, it is used as-is.
    """
    key = (role_id or "").strip()
    if not key:
        raise ValueError("role_id is required")
    role = get_role(key)
    raw = ""
    if role.chat and role.chat.workflow:
        raw = str(role.chat.workflow).strip()
    if not raw:
        raw = _DEFAULT_MAIN_WORKFLOW_BY_ROLE.get(key, "")
    if not raw:
        raise ValueError(
            f"Role {key!r} has no chat.workflow in role.yaml and no built-in default filename."
        )
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p.resolve()
    norm = str(p).replace("\\", "/")
    if norm.startswith(("assistants/", "gui/", "config/")):
        return (_REPO_ROOT / p).resolve()
    return (_ROLES_ROOT / key / p).resolve()
