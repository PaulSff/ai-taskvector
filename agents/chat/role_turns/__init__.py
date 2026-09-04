"""Per-role Flet chat wiring: ``RoleChatTurnContext`` + ``get_role_chat_handler`` + one handler per ``role_id``.

Built-in handlers live in subpackages (``workflow_designer/``, ``analyst/``, ``rl_coach/``); see ``README.md`` in this directory.
"""

from agents.chat.role_turns.protocol import RoleChatHandler
from agents.chat.role_turns.registry import (
    clear_dynamic_handler_cache,
    get_role_chat_handler,
)
from agents.chat.role_turns.turn_edits import set_commenter_for_new_comments

__all__ = [
    "RoleChatHandler",
    "clear_dynamic_handler_cache",
    "get_role_chat_handler",
    "set_commenter_for_new_comments",
]
