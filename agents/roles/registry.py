"""Load and cache role definitions from agents/roles/<id>/role.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

from agents.roles.chat_config import parse_role_chat_config
from agents.roles.types import RoleConfig, RoleIds
from agents.tools.types import ToolList
from core.schemas.primitives import Data

_ROLES_ROOT = Path(__file__).resolve().parent
_CACHE: dict[str, RoleConfig] = {}


def roles_definitions_dir() -> Path:
    """Directory containing ``<role_id>/role.yaml`` (the ``agents/roles`` package path)."""
    return _ROLES_ROOT


# Stable role ids (folder names under ``agents/roles/<id>/``).
WORKFLOW_DESIGNER_ROLE_ID = "workflow_designer"
RL_COACH_ROLE_ID = "rl_coach"
ANALYST_ROLE_ID = "analyst"
CODER_ROLE_ID = "coder"
PLANNER_ROLE_ID = "planner"
DEMIURGE_ROLE_ID = "demiurge"
RECEPTIONIST_ROLE_ID = "receptionist"
DISPATCHER_ROLE_ID = "dispatcher"

# Main Flet agents chat dropdown: order = UI order. Wire new agents in ``chat.py`` before extending.
CHAT_MAIN_agent_ROLE_IDS: tuple[str, ...] = (
    WORKFLOW_DESIGNER_ROLE_ID,
    ANALYST_ROLE_ID,
    RL_COACH_ROLE_ID,
    RECEPTIONIST_ROLE_ID,
    DEMIURGE_ROLE_ID,
    PLANNER_ROLE_ID,
    CODER_ROLE_ID,
)


def list_role_ids() -> RoleIds:
    """Return sorted role ids: each immediate child of ``agents/roles`` that contains ``role.yaml``."""
    names: list[str] = []
    for p in sorted(_ROLES_ROOT.iterdir()):
        if p.is_dir() and (p / "role.yaml").is_file():
            names.append(p.name)
    return tuple(names)


def _coerce_tools(raw: Any) -> ToolList:
    if raw is None:
        return ()
    if isinstance(raw, list):
        return tuple(str(x).strip() for x in raw if str(x).strip())
    return ()


def _load_yaml(role_id: str) -> Data:
    path = _ROLES_ROOT / role_id / "role.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Role file not found: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise TypeError(f"role.yaml for {role_id!r} must be a mapping")

    return data


def _build_config(role_id: str, data: Data) -> RoleConfig:
    rid = str(data.get("id") or role_id).strip()

    if rid != role_id:
        raise ValueError(
            f"role.yaml id {rid!r} does not match folder {role_id!r}"
        )

    role_name = str(
        data.get("role_name")
        or data.get("display_name")
        or role_id
    ).strip()

    name = str(data.get("name") or "").strip()
    project_name = str(data.get("project_name") or "").strip()

    intro_raw = data.get("introduction_words")
    introduction_words = (
        str(intro_raw).strip() if intro_raw is not None else ""
    )

    resp_raw = data.get("responsibility_description")
    responsibility_description = (
        str(resp_raw).strip() if resp_raw is not None else ""
    )

    fur = data.get("follow_up_max_rounds")

    if fur is None or fur == "":
        follow_up: int | None = None
    elif isinstance(fur, bool):
        raise TypeError(
            "role.yaml field 'follow_up_max_rounds' must be an integer"
        )
    elif isinstance(fur, int):
        follow_up = max(1, min(50, fur))
    elif isinstance(fur, str):
        try:
            follow_up_value = int(fur.strip())
        except ValueError as exc:
            raise TypeError(
                "role.yaml field 'follow_up_max_rounds' must be an integer"
            ) from exc

        follow_up = max(1, min(50, follow_up_value))
    else:
        raise TypeError(
            "role.yaml field 'follow_up_max_rounds' must be an integer"
        )

    raw_llm = data.get("llm")

    if raw_llm is None:
        llm: Data = {}
    elif isinstance(raw_llm, dict):
        llm = {}

        for key, value in raw_llm.items():
            if not isinstance(key, str):
                raise TypeError(
                    "role.yaml field 'llm' must contain string keys"
                )
            llm[key] = value
    else:
        raise TypeError("role.yaml field 'llm' must be a mapping")

    provider_raw = llm.get("provider", "")
    ollama_host_raw = llm.get("ollama_host", "")
    ollama_model_raw = llm.get("ollama_model", "")

    if not isinstance(provider_raw, str):
        raise TypeError("role.yaml field 'llm.provider' must be a string")

    if not isinstance(ollama_host_raw, str):
        raise TypeError(
            "role.yaml field 'llm.ollama_host' must be a string"
        )

    if not isinstance(ollama_model_raw, str):
        raise TypeError(
            "role.yaml field 'llm.ollama_model' must be a string"
        )

    chat_config = parse_role_chat_config(data.get("chat"))

    known = {
        "id",
        "role_name",
        "display_name",
        "name",
        "project_name",
        "introduction_words",
        "responsibility_description",
        "follow_up_max_rounds",
        "tools",
        "chat",
        "use_legacy_followups",
        "rag",
        "llm",
        "settings",
        "report",
    }

    extra = {
        key: value
        for key, value in data.items()
        if key not in known
    }

    return RoleConfig(
        id=rid,
        role_name=role_name,
        name=name,
        project_name=project_name,
        introduction_words=introduction_words,
        responsibility_description=responsibility_description,
        follow_up_max_rounds=follow_up,
        tools=_coerce_tools(data.get("tools")),
        chat=chat_config,
        provider=provider_raw.strip(),
        ollama_host=ollama_host_raw.strip(),
        ollama_model=ollama_model_raw.strip(),
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
    """True if this role should appear in the main agents chat dropdown."""
    if role.chat is not None:
        return role.chat.enabled
    return role.id in CHAT_MAIN_agent_ROLE_IDS


def list_chat_dropdown_role_ids() -> RoleIds:
    """
    Role ids for the agents chat dropdown: ``CHAT_MAIN_agent_ROLE_IDS`` (when enabled), then
    any other role directory with ``role.yaml`` declaring ``chat.enabled: true``.
    """
    out: list[str] = []
    for rid in CHAT_MAIN_agent_ROLE_IDS:
        if is_role_chat_panel_enabled(get_role(rid)):
            out.append(rid)
    for rid in list_role_ids():
        if rid in CHAT_MAIN_agent_ROLE_IDS:
            continue
        if is_role_chat_panel_enabled(get_role(rid)):
            out.append(rid)
    return tuple(out)
