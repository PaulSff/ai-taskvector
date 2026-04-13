"""Load and cache role definitions from assistants/roles/<id>/role.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from assistants.roles.chat_config import parse_role_chat_config
from assistants.roles.types import RoleConfig

_ROLES_ROOT = Path(__file__).resolve().parent
_CACHE: dict[str, RoleConfig] = {}

# Stable role ids (folder names under ``assistants/roles/<id>/``).
WORKFLOW_DESIGNER_ROLE_ID = "workflow_designer"
RL_COACH_ROLE_ID = "rl_coach"
ANALYST_ROLE_ID = "analyst"

# Main Flet assistants chat dropdown: order = UI order. Wire new assistants in ``chat.py`` before extending.
CHAT_MAIN_ASSISTANT_ROLE_IDS: tuple[str, ...] = (
    WORKFLOW_DESIGNER_ROLE_ID,
    ANALYST_ROLE_ID,
    RL_COACH_ROLE_ID,
)


def list_role_ids() -> tuple[str, ...]:
    """Return sorted role ids: each immediate child of ``assistants/roles`` that contains ``role.yaml``."""
    names: list[str] = []
    for p in sorted(_ROLES_ROOT.iterdir()):
        if p.is_dir() and (p / "role.yaml").is_file():
            names.append(p.name)
    return tuple(names)


def _coerce_tools(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, list):
        return tuple(str(x).strip() for x in raw if str(x).strip())
    return ()


def _load_yaml(role_id: str) -> dict[str, Any]:
    path = _ROLES_ROOT / role_id / "role.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Role file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"role.yaml for {role_id!r} must be a mapping")
    return data


def _build_config(role_id: str, data: dict[str, Any]) -> RoleConfig:
    rid = str(data.get("id") or role_id).strip()
    if rid != role_id:
        raise ValueError(f"role.yaml id {rid!r} does not match folder {role_id!r}")
    role_name = str(data.get("role_name") or data.get("display_name") or role_id).strip()
    name = str(data.get("name") or "").strip()
    intro_raw = data.get("introduction_words")
    introduction_words = (str(intro_raw).strip() if intro_raw is not None else "")
    resp_raw = data.get("responsibility_description")
    responsibility_description = (str(resp_raw).strip() if resp_raw is not None else "")
    fur = data.get("follow_up_max_rounds")
    follow_up: int | None
    if fur is None or fur == "":
        follow_up = None
    else:
        follow_up = max(1, min(50, int(fur)))
    known = {
        "id",
        "role_name",
        "display_name",  # legacy alias for role_name only; consumed above, not stored
        "name",
        "introduction_words",
        "follow_up_max_rounds",
        "tools",
        "chat",
        "use_legacy_followups",
        "rag",
        "llm",
        "settings",
        "report",
    }
    extra = {k: v for k, v in data.items() if k not in known}
    return RoleConfig(
        id=rid,
        role_name=role_name,
        name=name,
        introduction_words=introduction_words,
        responsibility_description=responsibility_description,
        follow_up_max_rounds=follow_up,
        tools=_coerce_tools(data.get("tools")),
        chat=parse_role_chat_config(data.get("chat")),
        extra=extra,
    )


def get_role(role_id: str) -> RoleConfig:
    """
    Return cached RoleConfig for ``role_id`` (e.g. ``workflow_designer``, ``rl_coach``).
    """
    key = (role_id or "").strip()
    if not key:
        raise ValueError("role_id is required")
    if key in _CACHE:
        return _CACHE[key]
    cfg = _build_config(key, _load_yaml(key))
    _CACHE[key] = cfg
    return cfg


def clear_role_cache() -> None:
    """Tests only: reset cached roles after editing YAML."""
    _CACHE.clear()


def is_role_chat_panel_enabled(role: RoleConfig) -> bool:
    """True if this role should appear in the main assistants chat dropdown."""
    if role.chat is not None:
        return role.chat.enabled
    return role.id in CHAT_MAIN_ASSISTANT_ROLE_IDS


def list_chat_dropdown_role_ids() -> tuple[str, ...]:
    """
    Role ids for the assistants chat dropdown: ``CHAT_MAIN_ASSISTANT_ROLE_IDS`` (when enabled), then
    any other role directory with ``role.yaml`` declaring ``chat.enabled: true``.
    """
    out: list[str] = []
    for rid in CHAT_MAIN_ASSISTANT_ROLE_IDS:
        if is_role_chat_panel_enabled(get_role(rid)):
            out.append(rid)
    for rid in list_role_ids():
        if rid in CHAT_MAIN_ASSISTANT_ROLE_IDS:
            continue
        if is_role_chat_panel_enabled(get_role(rid)):
            out.append(rid)
    return tuple(out)
