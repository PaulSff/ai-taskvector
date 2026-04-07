"""
Central keyboard shortcut definitions and chainable handler.
All Cmd/Ctrl+key and Escape handling should use these so shortcuts stay consistent.
"""
from __future__ import annotations

from typing import Callable

import flet as ft


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
        return True
    return False


def is_edit_code_block_shortcut(e: ft.KeyboardEvent) -> bool:
    """True if event is Cmd+E or Ctrl+E."""
    return bool(e.key and (e.meta or e.ctrl) and e.key.lower() == "e")


def is_escape(e: ft.KeyboardEvent) -> bool:
    """True if event is Escape."""
    return e.key == "Escape"


def create_keyboard_handler(
    chain_to: Callable[[ft.KeyboardEvent], None] | None,
    *,
    on_save: Callable[[], None] | None = None,
    on_undo: Callable[[], None] | None = None,
    on_redo: Callable[[], None] | None = None,
    on_find: Callable[[], None] | None = None,
    on_escape: Callable[[], None] | None = None,
    on_edit_code_block: Callable[[], None] | None = None,
) -> Callable[[ft.KeyboardEvent], None]:
    """
    Build a keyboard handler that runs the given callbacks for shortcuts, then chains to chain_to.

    Use in main.py with on_save=<fn that saves and shows toast>; use in code view / dialogs
    with on_find=show_find_bar, on_escape=hide_find_bar and chain_to=previous page.on_keyboard_event.
    """

    def handler(e: ft.KeyboardEvent) -> None:
        if is_save_shortcut(e) and on_save is not None:
            on_save()
            return
        if is_undo_shortcut(e) and on_undo is not None:
            on_undo()
            return
        if is_redo_shortcut(e) and on_redo is not None:
            on_redo()
            return
        if is_find_shortcut(e) and on_find is not None:
            on_find()
            return
        if is_edit_code_block_shortcut(e) and on_edit_code_block is not None:
            on_edit_code_block()
            return
        if is_escape(e) and on_escape is not None:
            on_escape()
            return
        if chain_to is not None:
            chain_to(e)

    return handler