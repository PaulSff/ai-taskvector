from __future__ import annotations

from typing import Any, Callable

import flet as ft


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
    if role not in ("user", "assistant"):
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


def build_message_row(
    *,
    page: ft.Page,
    msg: dict[str, Any],
    persist: Callable[[], None],
    toast: Callable[[str], None],
    now_ts: Callable[[], str] | None = None,
    bubble_width: int | None = 420,
) -> ft.Row:
    role = msg.get("role")
    content = msg.get("content") or ""
    is_user = role == "user"
    row_align = ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START
    text_color = ft.Colors.WHITE if is_user else ft.Colors.GREY_200

    bubble_is_expand = bubble_width is None
    bubble = ft.Container(
        content=ft.Text(
            str(content),
            color=text_color,
            size=12,
            selectable=True,
            no_wrap=False,
            width=bubble_width if bubble_width is not None else None,
        ),
        padding=ft.padding.symmetric(horizontal=10, vertical=6),
        border_radius=8,
        bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.WHITE)
        if is_user
        else ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
        width=bubble_width if bubble_width is not None else None,
        expand=True if bubble_is_expand else None,
    )

    def _save_feedback(value: str) -> None:
        fb: dict[str, Any] = {"type": "thumb", "value": value}
        if now_ts is not None:
            fb["ts"] = now_ts()
        msg["feedback"] = fb
        persist()
        toast("Thanks for the feedback!")

    feedback_bar: ft.Control | None = None
    if not is_user:
        feedback_bar = ft.Container(
            content=ft.Row(
                [
                    ft.IconButton(
                        icon=ft.Icons.THUMB_UP,
                        icon_size=16,
                        tooltip="Good answer",
                        on_click=lambda _e: _save_feedback("up"),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.THUMB_DOWN,
                        icon_size=16,
                        tooltip="Bad answer",
                        on_click=lambda _e: _save_feedback("down"),
                    ),
                ],
                spacing=0,
            ),
            width=bubble_width if bubble_width is not None else None,
            expand=True if bubble_is_expand else None,
            padding=ft.padding.only(left=2, right=2, top=0, bottom=0),
        )

    row_children: list[ft.Control]
    content_stack: ft.Control = bubble if feedback_bar is None else ft.Column([bubble, feedback_bar], spacing=0)
    if bubble_is_expand:
        # Ensure the bubble gets a real width constraint so Text wraps.
        pad = ft.padding.only(left=12) if not is_user else None
        row_children = [ft.Container(expand=True, content=content_stack, padding=pad)]
    else:
        if is_user:
            row_children = [ft.Container(expand=True), content_stack]
        else:
            row_children = [content_stack, ft.Container(expand=True)]

    return ft.Row(row_children, alignment=row_align)


def render_messages(
    *,
    messages_col: ft.Column,
    chat_title_txt: ft.Text,
    history: list[dict[str, Any]],
    new_id: Callable[[], str],
    now_ts: Callable[[], str],
    row_builder: Callable[[dict[str, Any]], ft.Row],
) -> None:
    messages_col.controls = [chat_title_txt]
    for m in history:
        nm = normalize_message(m, new_id=new_id, now_ts=now_ts)
        if nm is None:
            continue
        messages_col.controls.append(row_builder(nm))

