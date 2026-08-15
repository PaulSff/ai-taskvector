# agents/chat/turn_status_hook.py
from __future__ import annotations

from collections.abc import Callable, Coroutine

import flet as ft

from gui.components.chat_panel.ui.progress_bar import TurnProgressBar


def on_turn_status_hook(
    page: ft.Page,
    bar: TurnProgressBar,
) -> Callable[[dict[str, object]], Coroutine[object, object, None]]:
    async def on_turn_status(payload: dict[str, object]) -> None:
        status_obj = payload.get("status")
        messenger_obj = payload.get("messenger")

        status = status_obj if isinstance(status_obj, str) else None

        messenger: str | None
        if messenger_obj is None:
            messenger = None
        elif isinstance(messenger_obj, str):
            messenger = messenger_obj
        else:
            messenger = None  # non-string messenger is ignored

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
