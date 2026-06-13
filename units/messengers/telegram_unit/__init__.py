"""TelegramClient unit: allows to interact with TDLib local client using both action commands and official methods."""

from .telegram_unit import (
    TELEGRAM_CLIENT_INPUT_PORTS,
    TELEGRAM_CLIENT_OUTPUT_PORTS,
    register_telegram_client,
)

__all__ = [
    "register_telegram_client",
    "TELEGRAM_CLIENT_INPUT_PORTS",
    "TELEGRAM_CLIENT_OUTPUT_PORTS",
]
