from __future__ import annotations

import re
import json
from typing import Any, Callable
import flet as ft

from gui.flet.tools.code_editor import build_code_display

# Regex for fenced code blocks (```lang\n...\```)
_FENCE_RE = re.compile(r"```(?P<lang>[A-Za-z0-9_+-]+)?\n(?P<body>[\s\S]*?)```", re.MULTILINE)


def _split_fenced_blocks(text: str) -> list[tuple[str, str | None, str]]:
    """Split text into ("text", None, chunk) and ("code", lang, body) segments."""
    parts: list[tuple[str, str | None, str]] = []
    last = 0
    for m in _FENCE_RE.finditer(text):
        if m.start() > last:
            parts.append(("text", None, text[last:m.start()]))
        lang = m.group("lang") or None
        body = m.group("body") or ""
        parts.append(("code", lang, body))
        last = m.end()
    if last < len(text):
        parts.append(("text", None, text[last:]))
    return parts


def _format_action_block(parsed: dict[str, Any] | None, raw: str) -> str:
    """Convert parsed action JSON into readable text. Return raw if no action."""
    if not isinstance(parsed, dict):
        return raw
    action = parsed.get("action")
    if action == "no_edit":
        reason = parsed.get("reason", "No reason provided")
        return f"No edits were made. Reason: {reason}"
    return raw


def _extract_edit_action(parsed: Any) -> str | None:
    """Return first non-no_edit action found in dict, list, or {'edits': [...]}."""
    if not parsed:
        return None
    if isinstance(parsed, dict):
        action = parsed.get("action")
        if action not in (None, "no_edit"):
            return action
        edits = parsed.get("edits")
        if isinstance(edits, list):
            for e in edits:
                if isinstance(e, dict):
                    a = e.get("action")
                    if a not in (None, "no_edit"):
                        return a
        return None
    if isinstance(parsed, list):
        for e in parsed:
            if isinstance(e, dict):
                a = e.get("action")
                if a not in (None, "no_edit"):
                    return a
    return None


def _render_assistant_content(
    *,
    page: ft.Page,
    toast: Callable[[str], None],
    on_undo: Callable[[], None] | None,
    on_redo: Callable[[], None] | None,
    applied: bool,
    apply_failed: bool,
    content: str,
    bubble_width: int | None,
) -> ft.Control:
    """Render assistant content with fenced code blocks, edit counts, and failures."""
    segments = _split_fenced_blocks(content)
    controls: list[ft.Control] = []

    text_style = ft.TextStyle(size=12, color=ft.Colors.GREY_200)
    border_color = ft.Colors.with_opacity(0.18, ft.Colors.WHITE)

    for kind, lang, chunk in segments:
        if not chunk:
            continue

        if kind == "text":
            controls.append(
                ft.Text(
                    chunk,
                    style=text_style,
                    selectable=True,
                    no_wrap=False,
                    width=bubble_width if bubble_width is not None else None,
                )
            )
            continue

        # --- Code block ---
        code_body_raw = chunk  # preserve all whitespace/newlines
        parsed: dict[str, Any] | list[dict[str, Any]] | None = None
        action_type: str | None = None
        edit_count = 0
        failed = False

        # Try single JSON object first
        try:
            parsed = json.loads(code_body_raw)
            action_type = _extract_edit_action(parsed)
        except Exception:
            # Fallback: multiple concatenated JSON
            objs: list[dict[str, Any]] = []
            decoder = json.JSONDecoder()
            idx = 0
            s = code_body_raw.strip()
            while idx < len(s):
                try:
                    obj, end = decoder.raw_decode(s, idx)
                    if isinstance(obj, dict):
                        objs.append(obj)
                    idx = end
                    while idx < len(s) and s[idx].isspace():
                        idx += 1
                except json.JSONDecodeError:
                    break
            if objs:
                parsed = objs
                action_type = _extract_edit_action(objs)

        # Count edits; failure comes from apply meta (LLM output has no success field)
        if isinstance(parsed, dict):
            if parsed.get("action") not in (None, "no_edit"):
                edit_count = 1
        elif isinstance(parsed, list):
            edit_count = sum(
                1
                for e in parsed
                if isinstance(e, dict) and e.get("action") not in (None, "no_edit")
            )
        failed = apply_failed and (action_type not in (None, "no_edit"))

        # Format the code block
        code_body = _format_action_block(
            parsed if isinstance(parsed, dict) else (parsed[0] if parsed else None),
            code_body_raw
        )
        is_no_edit = action_type == "no_edit"
        is_edit_action = action_type not in (None, "no_edit")

        # Build header text for edits/failures
        header_text = ""
        if is_edit_action:
            if edit_count > 0:
                header_text = f"{edit_count} edit{'s' if edit_count != 1 else ''}"
            if failed:
                header_text += " (failed)" if header_text else "Failed"

        # --- Clipboard, undo, redo handlers ---
        def _copy_code(_e: ft.ControlEvent, _text: str = code_body) -> None:
            async def _run() -> None:
                try:
                    await page.clipboard.set(_text)
                    toast("Copied!")
                except Exception:
                    pass
            page.run_task(_run)

        def _do_undo(_e: ft.ControlEvent) -> None:
            if on_undo:
                try: on_undo()
                except Exception: pass

        def _do_redo(_e: ft.ControlEvent) -> None:
            if on_redo:
                try: on_redo()
                except Exception: pass

        # --- Code block body: syntax-highlighted, collapsible (first N lines + Show more/less) ---
        code_lang = (lang or "json").strip().lower()
        if code_lang in ("js", "javascript"):
            code_lang = "javascript"
        elif code_lang not in ("json", "python", "javascript"):
            code_lang = "json"
        LINE_HEIGHT = 18
        COLLAPSED_LINES = 6
        lines = code_body.splitlines()
        total_lines = len(lines)
        if total_lines <= COLLAPSED_LINES:
            visible_text = code_body
            visible_height = max(1, total_lines) * LINE_HEIGHT
            show_toggle = False
        else:
            visible_text = "\n".join(lines[:COLLAPSED_LINES]) + "\n..."
            visible_height = (COLLAPSED_LINES + 1) * LINE_HEIGHT
            full_height = total_lines * LINE_HEIGHT
            show_toggle = True
        expanded_ref: list[bool] = [False]
        code_display_control, set_code_display, set_code_height = build_code_display(
            visible_text,
            language=code_lang,
            width=bubble_width,
            height=visible_height,
            page=page,
        )
        toggle_btn_ref: list[ft.IconButton | None] = [None]

        def _toggle_code_block(_e: ft.ControlEvent) -> None:
            if not show_toggle or toggle_btn_ref[0] is None:
                return
            expanded_ref[0] = not expanded_ref[0]
            if expanded_ref[0]:
                set_code_display(code_body)
                set_code_height(full_height)
                toggle_btn_ref[0].icon = ft.Icons.EXPAND_LESS
                toggle_btn_ref[0].tooltip = "Show less"
            else:
                set_code_display(visible_text)
                set_code_height(visible_height)
                toggle_btn_ref[0].icon = ft.Icons.EXPAND_MORE
                toggle_btn_ref[0].tooltip = "Show more"
            try:
                toggle_btn_ref[0].update()
                page.update()
            except Exception:
                pass

        toggle_btn = ft.IconButton(
            icon=ft.Icons.EXPAND_MORE,
            icon_size=16,
            tooltip="Show more",
            on_click=_toggle_code_block,
            padding=2,
            style=ft.ButtonStyle(padding=2),
            visible=show_toggle,
        )
        toggle_btn_ref[0] = toggle_btn
        # --- Container ---
        controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Container(expand=True),
                                ft.Text(
                                    "Applied" if (applied and is_edit_action) else "",
                                    size=10,
                                    color=ft.Colors.GREEN_400,
                                    visible=bool(applied and is_edit_action),
                                ),
                                ft.Text(
                                    header_text,
                                    size=10,
                                    color=ft.Colors.ORANGE_300 if failed else ft.Colors.GREY_400,
                                    visible=bool(header_text),
                                ),
                                ft.IconButton(icon=ft.Icons.UNDO, icon_size=14, tooltip="Undo", on_click=_do_undo, padding=0, style=ft.ButtonStyle(padding=0), visible=is_edit_action, disabled=(on_undo is None)),
                                ft.IconButton(icon=ft.Icons.REDO, icon_size=14, tooltip="Redo", on_click=_do_redo, padding=0, style=ft.ButtonStyle(padding=0), visible=is_edit_action, disabled=(on_redo is None)),
                                ft.IconButton(icon=ft.Icons.CONTENT_COPY, icon_size=14, tooltip="Copy", on_click=_copy_code, padding=0, style=ft.ButtonStyle(padding=0), visible=not is_no_edit),
                            ],
                            spacing=4,
                        ),
                        code_display_control,
                        ft.Row(
                            [ft.Container(expand=True), toggle_btn],
                            alignment=ft.MainAxisAlignment.END,
                            visible=show_toggle,
                        ),
                    ],
                    spacing=4,
                ),
                padding=ft.Padding.only(left=10, right=6, top=6, bottom=8),
                border=ft.border.all(1, border_color),
                border_radius=8,
                bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.WHITE),
            )
        )

    if not controls:
        return ft.Text(
            content,
            style=text_style,
            selectable=True,
            no_wrap=False,
            width=bubble_width if bubble_width is not None else None,
        )

    return ft.Column(controls, spacing=6)


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
    on_undo: Callable[[], None] | None = None,
    on_redo: Callable[[], None] | None = None,
    now_ts: Callable[[], str] | None = None,
    bubble_width: int | None = 420,
) -> ft.Row:
    role = msg.get("role")
    content = msg.get("content") or ""
    is_user = role == "user"
    row_align = ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START
    text_color = ft.Colors.WHITE if is_user else ft.Colors.GREY_200

    bubble_is_expand = bubble_width is None
    bubble_content: ft.Control
    if is_user:
        bubble_content = ft.Text(
            str(content),
            color=text_color,
            size=12,
            selectable=True,
            no_wrap=False,
            width=bubble_width if bubble_width is not None else None,
        )
    else:
        apply_meta = msg.get("apply")
        applied = False
        apply_failed = False
        if isinstance(apply_meta, dict) and bool(apply_meta.get("attempted")):
            if apply_meta.get("success") is True:
                applied = True
            else:
                apply_failed = True
        bubble_content = _render_assistant_content(
            page=page,
            toast=toast,
            on_undo=on_undo,
            on_redo=on_redo,
            applied=applied,
            apply_failed=apply_failed,
            content=str(content),
            bubble_width=bubble_width,
        )

    bubble = ft.Container(
        content=bubble_content,
        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
        border_radius=8,
        bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.WHITE)
        if is_user
        else ft.Colors.TRANSPARENT,
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
        fb_value: str | None = None
        fb = msg.get("feedback")
        if isinstance(fb, dict):
            v = fb.get("value")
            if v in ("up", "down"):
                fb_value = v

        up_btn: ft.IconButton | None = None
        down_btn: ft.IconButton | None = None

        def _apply_feedback_ui(value: str | None) -> None:
            nonlocal up_btn, down_btn
            if up_btn is None or down_btn is None:
                return
            # Highlight the selected rating; keep the other neutral.
            up_btn.icon_color = ft.Colors.GREEN_400 if value == "up" else ft.Colors.GREY_500
            down_btn.icon_color = ft.Colors.RED_400 if value == "down" else ft.Colors.GREY_500
            try:
                up_btn.update()
                down_btn.update()
            except Exception:
                pass

        feedback_bar = ft.Container(
            content=ft.Row(
                [
                    ft.IconButton(
                        icon=ft.Icons.THUMB_UP,
                        icon_size=16,
                        tooltip="Good answer",
                        on_click=lambda _e: (_save_feedback("up"), _apply_feedback_ui("up")),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.THUMB_DOWN,
                        icon_size=16,
                        tooltip="Bad answer",
                        on_click=lambda _e: (_save_feedback("down"), _apply_feedback_ui("down")),
                    ),
                ],
                spacing=0,
            ),
            width=bubble_width if bubble_width is not None else None,
            expand=True if bubble_is_expand else None,
            padding=ft.Padding.only(left=2, right=2, top=0, bottom=0),
        )
        # Capture refs so we can update colors on click and initial render.
        try:
            row = feedback_bar.content  # type: ignore[assignment]
            if isinstance(row, ft.Row) and len(row.controls) >= 2:
                if isinstance(row.controls[0], ft.IconButton):
                    up_btn = row.controls[0]
                if isinstance(row.controls[1], ft.IconButton):
                    down_btn = row.controls[1]
        except Exception:
            pass
        _apply_feedback_ui(fb_value)

    row_children: list[ft.Control]
    content_stack: ft.Control = bubble if feedback_bar is None else ft.Column([bubble, feedback_bar], spacing=0)
    if bubble_is_expand:
        # Ensure the bubble gets a real width constraint so Text wraps.
        pad = ft.Padding.only(left=12) if not is_user else None
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

