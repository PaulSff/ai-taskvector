# gui/chat/turn_status_hook.py
from __future__ import annotations

from typing import Any

import flet as ft

from gui.chat.ui.progress_bar import TurnProgressBar


def on_turn_status_hook(
    page: ft.Page, bar: TurnProgressBar
):
    async def on_turn_status(payload: dict[str, Any]) -> None:
        status = payload.get("status")
        messenger = payload.get("messenger")

        if status == "running":
            await bar.set_running(messenger)
        elif status == "working":
            await bar.set_working()
        elif status == "applying":
            await bar.set_applying()
        elif status == "done":
            await bar.set_done()

        page.update()

    return on_turn_status
