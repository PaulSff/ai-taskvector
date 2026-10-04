from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import flet as ft

from agents.chat.session.state import AgentChatHistory
from gui.components.chat_panel.ui.render_agent_content import render_agent_content
from gui.components.chat_panel.ui.render_helpers import (
    OPEN_FENCE_LINE,
    build_feedback_thumbs,
)
from gui.utils.keyboard_commands import KeyboardCallback
from gui.utils.notifications import ToastCallback

type RowBuilder = Callable[[dict[str, Any]], Awaitable[ft.Row]]

def streaming_agent_opened_code_fence(text: str) -> bool:
    """True once the buffer has a complete opening fence line (triple backtick, optional lang, newline)."""
    return OPEN_FENCE_LINE.search(text) is not None


async def build_agent_streaming_body(
    *,
    page: ft.Page,
    toast: ToastCallback,
    on_undo: KeyboardCallback | None,
    on_redo: KeyboardCallback | None,
    content: str,
    bubble_width: int | None,
) -> ft.Control:
    """Same rendering as a finished agent bubble, for in-progress streamed content (incl. incomplete fences)."""
    return await render_agent_content(
        page=page,
        toast=toast,
        on_undo=on_undo,
        on_redo=on_redo,
        applied=False,
        apply_failed=False,
        content=content,
        bubble_width=bubble_width,
    )


def normalize_message(
    m: Any,
    *,
    new_id: Callable[[], str],
    now_ts: Callable[[], str],
) -> dict[str, Any] | None:
    """Ensure minimal fields exist and types are sane."""
    if not isinstance(m, dict):
        return None
    role = m.get("role")
    if role not in ("user", "agent"):
        return None
    content = m.get("content")
    if not isinstance(content, str):
        content = "" if content is None else str(content)
    if not m.get("id"):
        m["id"] = new_id()
    if not m.get("ts"):
        m["ts"] = now_ts()
    m["role"] = role
    m["content"] = content
    return m


async def render_messages(
    *,
    messages_col: ft.Column,
    chat_title_txt: ft.Text,
    history: AgentChatHistory,
    new_id: Callable[[], str],
    now_ts: Callable[[], str],
    row_builder: RowBuilder,
) -> None:
    messages_col.controls = [chat_title_txt]
    for m in history:
        nm = normalize_message(m, new_id=new_id, now_ts=now_ts)
        if nm is None:
            continue
        row = await row_builder(nm)
        nm["_flet_row"] = row
        messages_col.controls.append(row)


async def build_message_row(
    *,
    page: ft.Page,
    msg: dict[str, Any],
    persist: Callable[[], None],
    toast: ToastCallback,
    on_undo: KeyboardCallback | None = None,
    on_redo:  KeyboardCallback | None = None,
    bubble_width: int | None = None,
    key: str | float | bool | None = None,
) -> ft.Row:

    role = msg.get("role")

    content = str(msg.get("content") or "")

    is_user = role == "user"

    row_align = ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START

    if is_user:
        bubble_content: ft.Control = ft.Text(
            content,
            color=ft.Colors.GREY_200,
            size=12,
            selectable=True,
            no_wrap=False,
            width=bubble_width,
        )

    else:
        # Derive applied / apply_failed from the stored workflow metadata so that
        # status badges ("Applied", undo/redo, etc.) survive page reload and the
        # smooth-inline row promotion in _append.
        _wf = msg.get("workflow_response") or {}
        _result_kind = _wf.get("result_kind") or ""
        _msg_applied = _result_kind == "applied"
        _msg_apply_failed = _result_kind == "apply_failed"
        bubble_content = await render_agent_content(
            page=page,
            toast=toast,
            on_undo=on_undo,
            on_redo=on_redo,
            applied=_msg_applied,
            apply_failed=_msg_apply_failed,
            content=content,
            bubble_width=bubble_width,
        )

    bubble = ft.Container(
        content=bubble_content,
        padding=ft.Padding.symmetric(
            horizontal=10,
            vertical=6,
        ),
        border_radius=6,
        bgcolor=(
            ft.Colors.with_opacity(
                0.10,
                ft.Colors.WHITE,
            )
            if is_user
            else ft.Colors.TRANSPARENT
        ),
        width=bubble_width if bubble_width is not None else None,
        # For agent messages the wrapping Column handles horizontal expansion.
        expand=(bubble_width is None) if is_user else False,
    )

    row_controls: list[ft.Control]

    if is_user:
        if bubble_width is None:
            row_controls = [
                ft.Container(width=12),  # fixed gutter on left for user messages
                bubble,
            ]
        else:
            row_controls = [
                ft.Container(expand=True),
                bubble,
            ]
    else:
        feedback_row = build_feedback_thumbs(msg, persist)
        agent_col = ft.Column(
            controls=[bubble, feedback_row],
            spacing=2,
            expand=(bubble_width is None),
        )
        if bubble_width is None:
            row_controls = [
                agent_col,
                ft.Container(width=12),  # fixed gutter on right for agent messages
            ]
        else:
            row_controls = [
                agent_col,
                ft.Container(expand=True),
            ]

    return ft.Row(
        key=key,
        controls=row_controls,
        alignment=row_align,
    )



__all__ = [
    "build_agent_streaming_body",
    "build_message_row",
    "render_messages",
    "streaming_agent_opened_code_fence",
]
