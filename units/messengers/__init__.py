"""Messengers environment units: TelegramClient and future messenger integrations."""

import logging

from units.messengers.telegram_bot import (
    register_ptb_telegram_bot,
)
from units.messengers.telegram_client import (
    register_telegram_client,
)
from units.registry import UNIT_REGISTRY

logger = logging.getLogger(__name__)

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
        from units.env_loaders import register_env_loader
    except ImportError:
        logger.info("env_loaders not available; cannot register messengers env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_env_loader for messengers")
        raise

    try:
        from units.messengers import register_messengers_units
    except ImportError:
        logger.info("units.messengers not available; cannot register messengers env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_messengers_units")
        raise

    try:
        register_env_loader("messengers", register_messengers_units)
    except Exception:
        logger.exception("Failed to register messengers env loader")
        raise


_register_messengers_env_loader()

__all__ = ["register_messengers_units"]
