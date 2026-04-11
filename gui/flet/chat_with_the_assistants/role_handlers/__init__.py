"""Per-role Flet chat wiring: ``RoleChatTurnContext`` + ``get_role_chat_handler`` + one handler per ``role_id``."""

from gui.flet.chat_with_the_assistants.role_handlers.context import RoleChatTurnContext
from gui.flet.chat_with_the_assistants.role_handlers.protocol import RoleChatHandler
from gui.flet.chat_with_the_assistants.role_handlers.registry import (
    clear_dynamic_handler_cache,
    get_role_chat_handler,
)

__all__ = [
    "RoleChatHandler",
    "RoleChatTurnContext",
    "clear_dynamic_handler_cache",
    "get_role_chat_handler",
]
