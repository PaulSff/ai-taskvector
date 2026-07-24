from __future__ import annotations

import asyncio

import flet as ft


class TurnProgressBar:
    def __init__(self) -> None:
        self.bar = ft.ProgressBar(
            value=0.0,
            visible=False,
            height=1
        )
        self._anim_task: asyncio.Task[None] | None = None

    def control(self) -> ft.Control:
        return self.bar

    async def animate_to(
        self,
        target: float,
        *,
        steps: int = 12,
        delay_s: float = 0.015,
    ) -> None:
        start = float(self.bar.value or 0.0)
        if self._anim_task is not None and not self._anim_task.done():
            self._anim_task.cancel()

        async def _run() -> None:
            for i in range(1, steps + 1):
                self.bar.value = start + (target - start) * (i / steps)
                self.bar.visible = True
                await asyncio.sleep(delay_s)
            self.bar.value = target
            self.bar.visible = True

        self._anim_task = asyncio.create_task(_run())
        try:
            await self._anim_task
        except asyncio.CancelledError:
            pass

    async def set_running(self, messenger: str | None = None) -> None:
        await self.animate_to(0.2)

    async def set_working(self) -> None:
        await self.animate_to(0.6)

    async def set_applying(self) -> None:
        await self.animate_to(0.8)

    async def set_done(self) -> None:
        await self.animate_to(1.0)
        self.bar.visible = False
