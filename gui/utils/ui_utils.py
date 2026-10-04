from __future__ import annotations

import logging
from typing import Any

import flet as ft

from gui.utils.notifications import show_toast
from services.logging import setup_colored_logging

logger = setup_colored_logging(logging.DEBUG)


def _is_destroyed_session_error(exc: RuntimeError) -> bool:
    return "destroyed session" in str(exc).lower()

def _is_not_mounted_error(exc: RuntimeError) -> bool:
    message = str(exc).lower()
    return (
        "must be added to the page first" in message
        or "control must be added to the page" in message
    )

def safe_update(*controls: Any) -> None:
    """Update mounted Flet controls.

    Ignore controls that are not mounted yet or whose session was destroyed.
    Re-raise unrelated RuntimeErrors.
    """
    for control in controls:
        if control is None:
            continue

        try:
            control.update()
        except RuntimeError as exc:
            if (
                _is_destroyed_session_error(exc)
                or _is_not_mounted_error(exc)
            ):
                continue
            raise
        except AttributeError:
            # The control may have been detached during teardown.
            logger.warning("Skipped update for detached control", exc_info=True)


def safe_page_update(page: ft.Page | None) -> None:
    if page is None:
        return

    try:
        page.update()
    except RuntimeError as exc:
        if not _is_destroyed_session_error(exc):
            raise


async def _toast(page: ft.Page, msg: str) -> None:
    await show_toast(page, msg)
