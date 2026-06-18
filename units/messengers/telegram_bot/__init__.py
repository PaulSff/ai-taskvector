"""TelegramClient unit: Allows to interact with Telegram Bot API via python-telegram-bot lib"""

from .telegram_bot import (
    TELEGRAM_BOT_INPUT_PORTS,
    TELEGRAM_BOT_OUTPUT_PORTS,
    register_ptb_telegram_bot,
)

__all__ = [
    "register_ptb_telegram_bot",
    "TELEGRAM_BOT_INPUT_PORTS",
    "TELEGRAM_BOT_OUTPUT_PORTS",
]
