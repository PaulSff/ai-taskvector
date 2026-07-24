"""Per-role Flet chat wiring: ``RoleChatTurnContext`` + ``get_role_chat_handler`` + one handler per ``role_id``.

Built-in handlers live in subpackages (``workflow_designer/``, ``analyst/``, ``rl_coach/``); see ``README.md`` in this directory.
"""

from agents.chat.role_turns.context import RoleChatTurnContext
from agents.chat.role_turns.protocol import RoleChatHandler
from agents.chat.role_turns.registry import (
    clear_dynamic_handler_cache,
    get_role_chat_handler,
)
from agents.chat.role_turns.turn_edits import canonicalize_add_comment_edits

__all__ = [
    "RoleChatHandler",
    "RoleChatTurnContext",
    "canonicalize_add_comment_edits",
    "clear_dynamic_handler_cache",
    "get_role_chat_handler",
]
