"""Messengers environment units: TelegramClient and future messenger integrations."""

from units.env_loaders import register_env_loader
from units.messengers.telegram_bot import (
    register_ptb_telegram_bot,
)
from units.messengers.telegram_client import (
    register_telegram_client,
)
from units.registry import UNIT_REGISTRY

_MESSENGERS_TYPE_NAMES = (
    "TelegramBot",
    "TelegramClient",
)
for name in _MESSENGERS_TYPE_NAMES:
    spec = UNIT_REGISTRY.get(name)
    if spec is not None:
        spec.environment_tags = ["messengers"]


def register_messengers_units() -> None:
    """Register messenger-tagged units (TelegramClient, etc.)."""
    register_telegram_client()
    register_ptb_telegram_bot()


def _register_messengers_env_loader() -> None:
    try:
        register_env_loader("messengers", register_messengers_units)
    except Exception:
        pass


_register_messengers_env_loader()

__all__ = ["register_messengers_units"]
