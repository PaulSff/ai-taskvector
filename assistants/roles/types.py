"""Role configuration loaded from assistants/roles/<role_id>/role.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from assistants.roles.chat_config import RoleChatConfig


@dataclass(frozen=True)
class RoleConfig:
    """
    Assistant persona: metadata and knobs for follow-ups / tools.

    ``follow_up_max_rounds`` None means "use app settings" (Workflow Designer only today).

    ``name``: Human first name used in prompts / persona.
    ``introduction_words``: Opening self-introduction paragraph for the system prompt.
    ``role_name``: Short label for UI (dropdown, settings), e.g. "Analyst".
    ``responsibility_description``: Short text for semantic routing / task delegation (not shown in the main chat prompt by default).
    """

    id: str
    role_name: str
    name: str
    introduction_words: str
    responsibility_description: str = ""
    follow_up_max_rounds: int | None = None
    tools: tuple[str, ...] = ()
    chat: RoleChatConfig | None = None
    extra: dict[str, Any] = field(default_factory=dict)
