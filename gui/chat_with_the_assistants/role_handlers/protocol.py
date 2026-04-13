"""Protocol for one assistants-chat role (one ``role_id``)."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from gui.chat_with_the_assistants.role_handlers.context import RoleChatTurnContext


@runtime_checkable
class RoleChatHandler(Protocol):
    """Owns one role's chat turn: initial inputs, workflow path, and optional post-workflow hooks.

    Dev (-dev): after each workflow run, call ``record_llm_prompt_view_if_present(response, ctx.record_llm_prompt_view)``
    if the role’s runner merges ``attach_llm_prompt_debug_from_outputs`` into ``response`` (see ``llm_prompt_inspector``).
    """

    @property
    def role_id(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    async def run_turn(self, ctx: RoleChatTurnContext, *, message_for_workflow: str) -> None:
        """Run a single user → assistant turn for this role (see ``RoleChatTurnContext``)."""
        ...
