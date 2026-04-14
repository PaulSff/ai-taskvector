from __future__ import annotations

from typing import Any

import flet as ft


def safe_update(*controls: Any) -> None:
    """Best-effort update() that won't crash if control isn't mounted yet."""
    for c in controls:
        if c is None:
            continue
        try:
            c.update()
        except Exception:
            pass


def safe_page_update(page: ft.Page) -> None:
    try:
        page.update()
    except Exception:
        pass
