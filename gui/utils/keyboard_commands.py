"""
Central keyboard shortcut definitions and chainable handler.
All Cmd/Ctrl+key and Escape handling should use these so shortcuts stay consistent.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

import flet as ft

KeyboardCallback = Callable[[], Awaitable[None]]
KeyboardChainCallback = Callable[
    [ft.KeyboardEvent],
    Awaitable[None],
]

def is_save_shortcut(e: ft.KeyboardEvent) -> bool:
    """True if event is Cmd+S (macOS) or Ctrl+S (Windows/Linux)."""
    return bool(e.key and (e.meta or e.ctrl) and e.key.lower() == "s")


def is_find_shortcut(e: ft.KeyboardEvent) -> bool:
    """True if event is Cmd+F or Ctrl+F."""
    return bool(e.key and (e.meta or e.ctrl) and e.key.upper() == "F")


def is_undo_shortcut(e: ft.KeyboardEvent) -> bool:
    """True if event is Cmd+Z or Ctrl+Z."""
    return bool(e.key and (e.meta or e.ctrl) and not e.shift and e.key.upper() == "Z")


def is_redo_shortcut(e: ft.KeyboardEvent) -> bool:
    """True if event is Cmd+Shift+Z, Ctrl+Shift+Z, or Ctrl+Y."""
    if not e.key:
        return False
    k = e.key.upper()

    if (e.meta or e.ctrl) and e.shift and k == "Z":
        return True

    if e.ctrl and k == "Y":
        return bool(e.ctrl and k == "Y")

    return False



def is_edit_code_block_shortcut(e: ft.KeyboardEvent) -> bool:
    """True if event is Cmd+E or Ctrl+E."""
    return bool(e.key and (e.meta or e.ctrl) and e.key.lower() == "e")


def is_escape(e: ft.KeyboardEvent) -> bool:
    """True if event is Escape."""
    return e.key == "Escape"


def create_keyboard_handler(
    chain_to: KeyboardChainCallback | None,
    *,
    on_save: KeyboardCallback | None = None,
    on_undo: KeyboardCallback | None = None,
    on_redo: KeyboardCallback | None = None,
    on_find: KeyboardCallback | None = None,
    on_escape: KeyboardCallback | None = None,
    on_edit_code_block: KeyboardCallback | None = None,
) -> KeyboardChainCallback:
    """
    Build a keyboard handler that runs the given callbacks for shortcuts, then chains to chain_to.

    Use in main.py with on_save=<fn that saves and shows toast>; use in code view / dialogs
    with on_find=show_find_bar, on_escape=hide_find_bar and chain_to=previous page.on_keyboard_event.
    """

    async def handler(e: ft.KeyboardEvent) -> None:
        if is_save_shortcut(e) and on_save is not None:
            await on_save()
            return

        if is_undo_shortcut(e) and on_undo is not None:
            await on_undo()
            return

        if is_redo_shortcut(e) and on_redo is not None:
            await on_redo()
            return

        if is_find_shortcut(e) and on_find is not None:
            await on_find()
            return

        if is_edit_code_block_shortcut(e) and on_edit_code_block is not None:
            await on_edit_code_block()
            return

        if is_escape(e) and on_escape is not None:
            await on_escape()
            return

        if chain_to is not None:
            await chain_to(e)

    return handler
