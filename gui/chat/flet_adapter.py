# flet_adapter.py
"""
FletAdapter bridges ChatOrchestrator (async streaming events) to Flet UI.

Yields from orchestrator.send_user_message():
  - {"type":"status","status":...}              → sets inline status
  - {"type":"token","token":...,"partial":...}  → update stream bubble (plain/rich)
  - {"type":"inline_status","status":...}       → update inline status line
  - {"type":"final","message": {...}}           → commit final message to history
  - {"type":"error","error":...}                → show toast + clear busy

Usage:
  adapter = FletAdapter(
      orchestrator=orchestrator,
      ui_state=UIState(...),
      stream_queue=stream_queue,
  )
  asyncio.create_task(adapter.handle_turn(profile="analyst", text="hello"))
"""

from __future__ import annotations

import asyncio
import queue
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional, cast

import flet as ft
from role_handler_interface import RoleHandler, StreamingMetadata


# ─── UI State wrapper (minimal, avoids Flet-specific imports in orchestrator) ───────────────
@dataclass
class UIState:
    # Core Flet references
    messages_col: ft.Column
    stream_row_ref: list[Optional[ft.Row]]
    stream_plain_txt_ref: list[Optional[ft.Text]]
    stream_wrapper_ref: list[Optional[ft.Column]]
    stream_buffer_ref: list[str]
    stream_rich_ref: list[bool]

    # UI hooks
    prepare_stream_row: Callable[[], None]
    append_message: Callable[..., Dict[str, Any]]
    replace_agent_message_row: Callable[[Dict[str, Any]], None]

    # Optional hooks
    toast: Optional[Callable[[str], Any]] = None
    set_busy: Optional[Callable[[bool], Any]] = None


class FletAdapter:
    """
    Bridges async event-streaming from orchestrator → Flet UI.

    Adapts your orchestrator’s dict events to your Flet callbacks.
    """

    def __init__(self, ui_state: UIState):
        self.ui = ui_state

    async def handle_turn(
        self,
        orchestrator: "ChatOrchestrator",  # type: ignore[name-defined]  # forward ref
        profile: str,
        text: str,
        *,
        agent_display: Optional[str] = None,
        handler: Optional[RoleHandler] = None,
    ) -> None:
        """
        Entry point: invoke orchestrator.send_user_message, process events, update Flet.
        """
        # Reset stream state
        self.ui.prepare_stream_row()
        self.ui.stream_buffer_ref[0] = ""
        self.ui.stream_rich_ref[0] = False
        self.ui.stream_plain_txt_ref[0] = None

        # Run orchestrator and consume events
        async for event in orchestrator.send_user_message(
            profile=profile, text=text, agent_display=agent_display
        ):
            await self._on_event(event, handler or self._default_handler)

    # ─── Event dispatchers ───────────────────────────────────────────────

    async def _on_event(self, event: Dict[str, Any], handler: RoleHandler) -> None:
        match event["type"]:
            case "status":
                status = event.get("status")
                self._set_inline_status(status)
            case "token":
                token = event.get("token", "")
                self._on_token(token, handler)
            case "inline_status":
                st = event.get("status")
                self._set_inline_status(st)
            case "final":
                msg = event.get("message", {})
                await self._on_final_message(msg, handler)
            case "error":
                self._on_error(event.get("error", "Unknown error"))
            case _:
                print(f"[FletAdapter] Unknown event type: {event}")

    # ─── Handlers ────────────────────────────────────────────────────────

    async def _on_token(self, token: str, handler: RoleHandler) -> None:
        # Update handler buffer
        handler.append_chunk(token)

        # Update stream buffer (string accumulation for Flet)
        self.ui.stream_buffer_ref[0] += token

        # Detect rich mode (e.g., code fences) — reuse your existing logic
        from gui.chat.ui.message_renderer import streaming_agent_opened_code_fence

        if not self.ui.stream_rich_ref[0] and streaming_agent_opened_code_fence(
            self.ui.stream_buffer_ref[0]
        ):
            self.ui.stream_rich_ref[0] = True

        # Update Flet UI (throttled)
        await self._update_stream_row()

    async def _on_final_message(
        self, msg: Dict[str, Any], handler: RoleHandler
    ) -> None:
        # Finalize handler
        handler.end_stream()
        final_content = handler.get_final_message().get("content", "")

        # Optional: merge handler’s final content (e.g., if rich mode)
        if final_content:
            # Replace streaming bubble with final message
            final_msg = self.ui.append_message(
                msg.get("role", "agent"),
                final_content,
                meta={
                    **msg.get("meta", {}),
                    "turn_id": msg.get("id"),
                },
            )
            await self._finalize_stream_row(final_msg)
        else:
            # Use orchestrator’s final message directly
            final_msg = self.ui.append_message(
                msg.get("role", "agent"),
                msg.get("content", ""),
                meta={
                    **msg.get("meta", {}),
                    "turn_id": msg.get("id"),
                },
            )
            await self._finalize_stream_row(final_msg)

    async def _finalize_stream_row(self, final_msg: Dict[str, Any]) -> None:
        # Ensure stream row is cleared
        row = self.ui.stream_row_ref[0]
        if row and row in self.ui.messages_col.controls:
            self.ui.messages_col.controls.remove(row)
        self.ui.stream_row_ref[0] = None
        self.ui.stream_buffer_ref[0] = ""
        self.ui.stream_rich_ref[0] = False
        self.ui.messages_col.update()

    def _on_error(self, err: str) -> None:
        self.ui.toast and self.ui.toast(f"Error: {err}")
        self.ui.set_busy and self.ui.set_busy(False)

    # ─── UI helpers ──────────────────────────────────────────────────────

    async def _update_stream_row(self) -> None:
        """Refresh the streaming bubble (plain or rich)."""
        self.ui.prepare_stream_row()

        # Update bubble text
        content = self.ui.stream_buffer_ref[0]

        if self.ui.stream_rich_ref[0]:
            # Rich mode: delegate to your existing `build_agent_streaming_body()`
            from gui.chat.ui.message_renderer import (
                build_agent_streaming_body,
            )

            bubble = build_agent_streaming_body(
                page=self.ui.messages_col.page,
                toast=self.ui.toast or (lambda s: None),
                on_undo=None,  # or pass from outer scope
                on_redo=None,
                content=content,
                bubble_width=None,
            )

            # Replace wrapper content (keep same wrapper instance)
            if self.ui.stream_wrapper_ref[0]:
                self.ui.stream_wrapper_ref[0].controls[:] = [bubble]
                self.ui.stream_wrapper_ref[0].update()
        else:
            # Plain text
            txt = self.ui.stream_plain_txt_ref[0]
            if txt:
                txt.value = content
                txt.update()

        # Auto-scroll
        try:
            await self.ui.messages_col.scroll_to(offset=-1, duration=0)
        except Exception:
            pass

    def _set_inline_status(self, status: Optional[str]) -> None:
        # Hook to your StatusBarController
        # e.g., status_bar.set_status(status) if status else status_bar.set_status(None)
        # This method *must* be overridden or implemented by adapter consumer
        pass

    def _default_handler(self) -> RoleHandler:
        # Simple fallback handler
        class DefaultHandler:
            def __init__(self):
                self.content = ""
                self.role = "agent"

            def begin_stream(self, meta: StreamingMetadata) -> None:
                self.role = meta.role

            def append_chunk(self, chunk: str) -> None:
                self.content += chunk

            def end_stream(self) -> None:
                pass

            def get_final_message(self) -> dict[str, str]:
                return {"content": self.content}

        return DefaultHandler()


# ─── Utility: adapter factory (to wire into your existing `chat.py`) ───────────────────────
def create_flet_adapter_for_chat_panel(
    ui_state: UIState,
) -> FletAdapter:
    """
    Factory to create adapter with Flet-aware status callbacks.
    Assumes a `status_bar` object is accessible in scope.
    """

    class _Adapter(FletAdapter):
        def __init__(self, status_bar: Any):
            super().__init__(ui_state)
            self.status_bar = status_bar
            self._set_inline_status = status_bar.set_status

    return _Adapter  # type: ignore


# Optional: status_bar hook adapter (if StatusBarController in scope)
class StatusBarController:
    def __init__(self, set_status_fn: Callable[[Optional[str]], None]):
        self.set_status = set_status_fn
