"""Load and cache role definitions from agents/roles/<id>/role.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

from agents.roles.types import RoleConfig, RoleIds, parse_role_config
from agents.tools.types import ToolList
from core.schemas.primitives import Data

_ROLES_ROOT = Path(__file__).resolve().parent
_CACHE: dict[str, RoleConfig] = {}


def roles_definitions_dir() -> Path:
    """Return the directory containing ``<role_id>/role.yaml``."""
    return _ROLES_ROOT


# Stable role ids.
CHAT_NAME_CREATOR_ROLE_ID = "chat_name_creator"
WORKFLOW_DESIGNER_ROLE_ID = "workflow_designer"
RL_COACH_ROLE_ID = "rl_coach"
ANALYST_ROLE_ID = "analyst"
CODER_ROLE_ID = "coder"
PLANNER_ROLE_ID = "planner"
DEMIURGE_ROLE_ID = "demiurge"
RECEPTIONIST_ROLE_ID = "receptionist"
DISPATCHER_ROLE_ID = "dispatcher"


# Main Flet agents chat dropdown order.
CHAT_MAIN_AGENT_ROLE_IDS: tuple[str, ...] = (
    WORKFLOW_DESIGNER_ROLE_ID,
    ANALYST_ROLE_ID,
    RL_COACH_ROLE_ID,
    RECEPTIONIST_ROLE_ID,
    DEMIURGE_ROLE_ID,
    PLANNER_ROLE_ID,
    CODER_ROLE_ID,
)


def list_role_ids() -> RoleIds:
    """
    Return sorted role ids.

    A role is included when it is an immediate child directory containing
    ``role.yaml``.
    """
    names: list[str] = []

    for path in sorted(_ROLES_ROOT.iterdir()):
        if path.is_dir() and (path / "role.yaml").is_file():
            names.append(path.name)

    return tuple(names)


def _coerce_tools(raw: object) -> ToolList:
    if raw is None:
        return ()

    if not isinstance(raw, (list, tuple)):
        raise TypeError("role.yaml field 'tools' must be a list")

    tools: list[str] = []

    for value in raw:
        tool_name = str(value).strip()

        if tool_name:
            tools.append(tool_name)

    return tuple(tools)



def _load_yaml(role_id: str) -> Data:
    path = _ROLES_ROOT / role_id / "role.yaml"

    if not path.is_file():
        raise FileNotFoundError(f"Role file not found: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise TypeError(
            f"role.yaml for {role_id!r} must be a mapping"
        )

    return data


def _parse_follow_up_max_rounds(raw: object) -> int | None:
    if raw is None or raw == "":
        return None

    if isinstance(raw, bool):
        raise TypeError(
            "role.yaml field 'follow_up_max_rounds' must be an integer"
        )

    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str):
        text = raw.strip()

        if not text:
            return None

        try:
            value = int(text)
        except ValueError as exc:
            raise TypeError(
                "role.yaml field 'follow_up_max_rounds' must be an integer"
            ) from exc
    else:
        raise TypeError(
            "role.yaml field 'follow_up_max_rounds' must be an integer"
        )

    return max(1, min(50, value))



def _build_config(role_id: str, data: Data) -> RoleConfig:
    yaml_role_id = str(data.get("id") or role_id).strip()

    if yaml_role_id != role_id:
        raise ValueError(
            f"role.yaml id {yaml_role_id!r} does not match "
            f"folder {role_id!r}"
        )

    role_name = str(
        data.get("role_name")
        or data.get("display_name")
        or role_id
    ).strip()

    name = str(data.get("name") or "").strip()
    project_name = str(data.get("project_name") or "").strip()

    introduction_words = str(
        data.get("introduction_words") or ""
    ).strip()

    responsibility_description = str(
        data.get("responsibility_description") or ""
    ).strip()

    follow_up_max_rounds = _parse_follow_up_max_rounds(
        data.get("follow_up_max_rounds")
    )

    tools = _coerce_tools(data.get("tools"))

    parsed = parse_role_config(
        {
            **data,
            "id": yaml_role_id,
            "role_name": role_name,
            "name": name,
            "project_name": project_name,
            "introduction_words": introduction_words,
            "responsibility_description": responsibility_description,
            "follow_up_max_rounds": follow_up_max_rounds,
            "tools": tools,
        }
    )

    return parsed



def get_role(role_id: str) -> RoleConfig:
    """
    Return the cached configuration for ``role_id``.

    Example:

    ```python
    role = get_role("workflow_designer")
    ```
    """
    key = (role_id or "").strip()

    if not key:
        raise ValueError("role_id is required")

    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    config = _build_config(key, _load_yaml(key))
    _CACHE[key] = config

    return config


def clear_role_cache() -> None:
    """Clear cached roles, primarily for tests."""
    _CACHE.clear()


def is_role_chat_panel_enabled(role: RoleConfig) -> bool:
    """
    Return whether a role should appear in the main agents chat dropdown.

    Explicit ``chat.enabled`` takes precedence. Roles in the stable main-chat
    list remain enabled by default when no ``chat:`` block is present.
    """
    if role.chat_workflow is not None:
        return role.chat_enabled

    # ``chat:`` may exist without a workflow. Since the flattened provider_model does
    # not retain whether the YAML block was present, use the role's enabled
    # value for known roles and allow explicitly configured non-main roles
    # through their ``chat_enabled`` setting.
    if role.id in CHAT_MAIN_AGENT_ROLE_IDS:
        return role.chat_enabled

    return role.chat_enabled


def is_role_light_graph_mode_enabled(role_id: str) -> bool:
    """
    Return whether light graph mode is enabled for a role.

    The value is read from:
        chat.light_graph_mode
    in the role's role.yaml file.
    """
    role = get_role(role_id)
    return role.light_graph_mode


def list_chat_dropdown_role_ids() -> RoleIds:
    """
    Return role ids for the agents chat dropdown.

    Stable roles are returned first in UI order, followed by any other role
    declaring an enabled chat configuration.
    """
    output: list[str] = []

    for role_id in CHAT_MAIN_AGENT_ROLE_IDS:
        role = get_role(role_id)

        if is_role_chat_panel_enabled(role):
            output.append(role_id)

    for role_id in list_role_ids():
        if role_id in CHAT_MAIN_AGENT_ROLE_IDS:
            continue

        role = get_role(role_id)

        if is_role_chat_panel_enabled(role):
            output.append(role_id)

    return tuple(output)
