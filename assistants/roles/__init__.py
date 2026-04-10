"""Per-assistant role config (YAML + registry). Authoring: assistants/README.md."""
from __future__ import annotations

from assistants.roles.registry import clear_role_cache, get_role
from assistants.roles.types import RoleConfig

__all__ = ["RoleConfig", "clear_role_cache", "get_role"]
