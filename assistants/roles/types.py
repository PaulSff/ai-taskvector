"""Role configuration loaded from assistants/roles/<role_id>/role.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RoleConfig:
    """
    Assistant persona: metadata and knobs for follow-ups / skills.

    ``follow_up_max_rounds`` None means "use app settings" (Workflow Designer only today).
    """

    id: str
    display_name: str
    follow_up_max_rounds: int | None = None
    skills: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)
