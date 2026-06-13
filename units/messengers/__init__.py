"""Messengers environment units: TelegramClient and future messenger integrations."""

from units.env_loaders import register_env_loader
from units.messengers.telegram_unit import (
    TELEGRAM_CLIENT_INPUT_PORTS,
    TELEGRAM_CLIENT_OUTPUT_PORTS,
    register_telegram_client,
)


def register_messengers_units() -> None:
    """Register messenger-tagged units (TelegramClient, etc.)."""
    register_telegram_client()


register_env_loader("messengers", register_messengers_units)

__all__ = [
    "register_messengers_units",
    "register_telegram_client",
    "TELEGRAM_CLIENT_INPUT_PORTS",
    "TELEGRAM_CLIENT_OUTPUT_PORTS",
]
