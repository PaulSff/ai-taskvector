"""Per-assistant role config (YAML + registry). Authoring: assistants/README.md."""
from __future__ import annotations

from assistants.roles.chat_config import RoleChatConfig, parse_role_chat_config, role_chat_feature_enabled
from assistants.roles.registry import (
    ANALYST_ROLE_ID,
    CHAT_MAIN_ASSISTANT_ROLE_IDS,
    RL_COACH_ROLE_ID,
    WORKFLOW_DESIGNER_ROLE_ID,
    clear_role_cache,
    get_role,
    is_role_chat_panel_enabled,
    list_chat_dropdown_role_ids,
    list_role_ids,
)
from assistants.roles.types import RoleConfig
from assistants.roles.workflow_path import CHAT_NAME_CREATOR_ROLE_ID, get_role_chat_workflow_path

__all__ = [
    "ANALYST_ROLE_ID",
    "CHAT_NAME_CREATOR_ROLE_ID",
    "CHAT_MAIN_ASSISTANT_ROLE_IDS",
    "RL_COACH_ROLE_ID",
    "RoleChatConfig",
    "RoleConfig",
    "WORKFLOW_DESIGNER_ROLE_ID",
    "clear_role_cache",
    "get_role",
    "get_role_chat_workflow_path",
    "is_role_chat_panel_enabled",
    "list_chat_dropdown_role_ids",
    "list_role_ids",
    "parse_role_chat_config",
    "role_chat_feature_enabled",
]
