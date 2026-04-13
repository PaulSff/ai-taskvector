"""Per-role Flet chat wiring: ``RoleChatTurnContext`` + ``get_role_chat_handler`` + one handler per ``role_id``."""

from gui.chat.role_handlers.context import RoleChatTurnContext
from gui.chat.role_handlers.protocol import RoleChatHandler
from gui.chat.role_handlers.turn_edits import canonicalize_add_comment_edits
from gui.chat.role_handlers.registry import (
    clear_dynamic_handler_cache,
    get_role_chat_handler,
)

__all__ = [
    "RoleChatHandler",
    "RoleChatTurnContext",
    "canonicalize_add_comment_edits",
    "clear_dynamic_handler_cache",
    "get_role_chat_handler",
]
