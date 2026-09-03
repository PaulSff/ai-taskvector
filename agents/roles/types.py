"""Role configuration loaded from agents/roles/<role_id>/role.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.roles.chat_config import RoleChatConfig
from agents.tools.types import ToolList

type RoleIds = tuple[str, ...]

@dataclass(frozen=True)
class RoleConfig:
    """
    agent persona: metadata and knobs for follow-ups / tools.

    ``follow_up_max_rounds`` None means "use app settings" (Workflow Designer only today).

    ``name``: Human first name used in prompts / persona.
    ``introduction_words``: Opening self-introduction paragraph for the system prompt.
    ``role_name``: Short label for UI (dropdown, settings), e.g. "Analyst".
    ``responsibility_description``: Short text for semantic routing / task delegation (not shown in the main chat prompt by default).
    """

    id: str
    role_name: str
    name: str
    project_name: str
    introduction_words: str
    responsibility_description: str = ""
    follow_up_max_rounds: int | None = None
    tools: ToolList = ()
    chat: RoleChatConfig | None = None

    provider: str = ""
    ollama_host: str = ""
    ollama_model: str = ""

    extra: dict[str, object] = field(default_factory=dict)
