"""
Flet assistants chat panel: Workflow Designer / RL Coach in the right column.

Uses:
- assistants.prompts (system prompts)
- assistants.process_assistant_apply (apply graph edits)
- LLM_integrations.ollama (model API client)

This is the Flet equivalent of the Streamlit sketch in gui/app.py + gui/chat.py.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from threading import Thread
from typing import Any, Callable, Literal

import flet as ft

from assistants.process_assistant import process_assistant_apply
from assistants.prompts import RL_COACH_SYSTEM, WORKFLOW_DESIGNER_SYSTEM
from schemas.process_graph import ProcessGraph

from LLM_integrations import client as llm_client
from gui.flet.components.settings import get_chat_history_dir, get_llm_provider, get_llm_provider_config
from gui.flet.tools.notifications import show_toast

from gui.flet.chat_with_the_assistants.history_store import (
    load_chat_payload,
    slugify_filename,
    unique_path,
    write_chat_payload,
)
from gui.flet.chat_with_the_assistants.llm_client import suggest_chat_filename_base
from gui.flet.chat_with_the_assistants.message_renderer import build_message_row, render_messages
from gui.flet.chat_with_the_assistants.recent_chats_menu import RecentChatsMenu
from gui.flet.chat_with_the_assistants.state import ChatSessionState
from gui.flet.chat_with_the_assistants.ui_utils import safe_page_update, safe_update


AssistantType = Literal["Workflow Designer", "RL Coach"]

# Model options
OLLAMA_NUM_PREDICT = 1024
OLLAMA_TIMEOUT_S = 300

CHAT_HISTORY_SCHEMA_VERSION = 2

def _now_ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid4().hex


def _graph_summary(current_graph: Any) -> dict[str, Any]:
    """Reduce graph context to a small, LLM-friendly summary."""
    if isinstance(current_graph, dict):
        units = current_graph.get("units", []) or []
        conns = current_graph.get("connections", []) or []
        unit_summary = [
            {"id": u.get("id"), "type": u.get("type"), "controllable": bool(u.get("controllable", False))}
            for u in units
            if isinstance(u, dict)
        ]
        conn_summary = [
            {"from": c.get("from") or c.get("from_id"), "to": c.get("to") or c.get("to_id")}
            for c in conns
            if isinstance(c, dict)
        ]
        return {"units": unit_summary, "connections": conn_summary}
    if isinstance(current_graph, ProcessGraph):
        return {
            "units": [{"id": u.id, "type": u.type, "controllable": bool(u.controllable)} for u in current_graph.units],
            "connections": [{"from": c.from_id, "to": c.to_id} for c in current_graph.connections],
        }
    return {}


def _parse_all_json_blocks(content: str) -> list[Any]:
    """
    Extract all JSON blocks from LLM response.
    Prefers ```json fenced blocks.
    Falls back to scanning for balanced {...} blocks.
    """
    content = content.strip()
    results: list[Any] = []

    # Extract all fenced blocks
    fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)```", content)
    for block in fenced:
        try:
            obj = json.loads(block.strip())
            results.append(obj)
        except json.JSONDecodeError:
            continue

    if results:
        return results

    # Fallback: scan for multiple balanced {...}
    i = 0
    while i < len(content):
        if content[i] == "{":
            depth = 0
            start = i
            for j in range(i, len(content)):
                if content[j] == "{":
                    depth += 1
                elif content[j] == "}":
                    depth -= 1
                    if depth == 0:
                        raw = content[start : j + 1]
                        try:
                            obj = json.loads(raw)
                            results.append(obj)
                        except json.JSONDecodeError:
                            pass
                        i = j
                        break
            else:
                break
        i += 1

    return results



def _messages_from_history(history: list[dict[str, Any]], *, max_turn_pairs: int = 10) -> list[dict[str, str]]:
    """Convert local history to Ollama API messages (role/content)."""
    out: list[dict[str, str]] = []
    cap = max_turn_pairs * 2
    msgs = history[-cap:] if len(history) > cap else history
    for m in msgs:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content") or ""
        if isinstance(content, str):
            out.append({"role": role, "content": content})
    return out


async def _toast(page: ft.Page, msg: str) -> None:
    await show_toast(page, msg)


def build_assistants_chat_panel(
    page: ft.Page,
    *,
    graph_ref: list[ProcessGraph | None],
    set_graph: Callable[[ProcessGraph | None], None],
    on_undo: Callable[[], None] | None = None,
    on_redo: Callable[[], None] | None = None,
) -> ft.Control:
    """
    Build the right-column assistants chat panel.
    Applies Workflow Designer edits to the current graph.
    """
    assistant_dd = ft.Dropdown(
        label="Assistant",
        value="Workflow Designer",
        width=190,
        height=36,
        text_style=ft.TextStyle(size=12),
        options=[
            ft.dropdown.Option("Workflow Designer"),
            ft.dropdown.Option("RL Coach"),
        ],
    )

    def _assistant_profile_key(v: str | None) -> str:
        return "rl_coach" if (v or "").strip() == "RL Coach" else "workflow_designer"

    state = ChatSessionState(
        history=[],
        busy=False,
        has_sent_any=False,
        session_id=_new_id(),
        created_at=_now_ts(),
        chat_path=None,
    )

    # Track which input the user was using so we can restore focus after resizes.
    focus_pref: list[Literal["first", "bottom"] | None] = [None]

    # First-message input: placed at top, larger like Cursor.
    input_tf_first = ft.TextField(
        hint_text="Message...",
        multiline=True,
        min_lines=4,
        max_lines=12,
        shift_enter=True,  # Shift+Enter inserts newline; Enter submits
        expand=True,
        text_style=ft.TextStyle(size=12),
        border=ft.InputBorder.OUTLINE,
        border_radius=10,
        border_color=ft.Colors.GREY_700,
        focused_border_color=ft.Colors.BLUE_400,
        filled=True,
        fill_color=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
    )

    # Normal input: stays at bottom after first message.
    input_tf = ft.TextField(
        hint_text="Message...",
        multiline=True,
        min_lines=2,
        max_lines=6,
        shift_enter=True,
        expand=True,
        text_style=ft.TextStyle(size=12),
        border=ft.InputBorder.OUTLINE,
        border_radius=10,
        border_color=ft.Colors.GREY_700,
        focused_border_color=ft.Colors.BLUE_400,
        filled=True,
        fill_color=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
    )

    # Some Flet versions don't accept on_* in constructor; assign after creation.
    input_tf_first.on_focus = lambda _e: focus_pref.__setitem__(0, "first")
    input_tf.on_focus = lambda _e: focus_pref.__setitem__(0, "bottom")

    async def _focus_field(field: ft.TextField) -> None:
        # Retry focus a few times; resizes/layout changes can drop focus.
        for delay_s in (0.0, 0.05, 0.2, 0.5):
            try:
                await asyncio.sleep(delay_s)
                await field.focus()
                return
            except Exception:
                continue

    def _schedule_restore_focus() -> None:
        if state.busy:
            return
        which = focus_pref[0]
        if which == "bottom":
            async def _focus_bottom() -> None:
                await _focus_field(input_tf)

            page.run_task(_focus_bottom)
        elif which == "first":
            async def _focus_first() -> None:
                await _focus_field(input_tf_first)

            page.run_task(_focus_first)

    # Chain page resize handler (don't break other parts of the app).
    prev_on_resize = page.on_resize

    def _on_resize(e: Any) -> None:
        try:
            if callable(prev_on_resize):
                prev_on_resize(e)
        except Exception:
            pass
        _schedule_restore_focus()

    page.on_resize = _on_resize

    # --- Chat history persistence (auto-save) ---
    chat_history_dir = get_chat_history_dir()
    chat_history_dir.mkdir(parents=True, exist_ok=True)

    # Chat title.
    # Before first message: show above the first-message composer.
    # After first message: show at top of messages scroll area.
    chat_title_top_txt = ft.Text("new_chat", size=12, color=ft.Colors.GREY_500, visible=True)
    chat_title_txt = ft.Text("new_chat", size=12, color=ft.Colors.GREY_500, visible=False)

    messages_col = ft.Column(
        [chat_title_txt],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=8,
    )

    # Recent chats menu is created later (needs _load_chat_file callback).
    recent_menu_ref: list[RecentChatsMenu | None] = [None]

    def _recent_menu_refresh_and_select(filename: str | None) -> None:
        m = recent_menu_ref[0]
        if m is None:
            return
        m.refresh()
        m.set_selected(filename)

    def _set_chat_title(title: str) -> None:
        v = title or "new_chat"
        chat_title_top_txt.value = v
        chat_title_txt.value = v
        try:
            chat_title_top_txt.update()
            chat_title_txt.update()
        except Exception:
            pass

    def _set_chat_title_from_path(p: Path | None) -> None:
        if p is None:
            _set_chat_title("new_chat")
            return
        _set_chat_title(p.stem)

    def _persist_history() -> None:
        """Write current history to disk (best-effort)."""
        path = state.chat_path
        if path is None:
            return
        # Persist both profiles (sanitized) for debugging/replay.
        wd_provider = get_llm_provider(assistant="workflow_designer")
        wd_cfg = get_llm_provider_config(assistant="workflow_designer")
        rl_provider = get_llm_provider(assistant="rl_coach")
        rl_cfg = get_llm_provider_config(assistant="rl_coach")

        def _sanitize(cfg: dict[str, Any]) -> dict[str, Any]:
            safe: dict[str, Any] = {}
            for k, v in (cfg or {}).items():
                ks = str(k).lower()
                if any(s in ks for s in ("key", "token", "secret", "password")):
                    continue
                safe[str(k)] = v
            return safe
        payload = {
            "schema_version": CHAT_HISTORY_SCHEMA_VERSION,
            "session_id": state.session_id,
            "created_at": state.created_at,
            "assistant_selected": assistant_dd.value,
            "llm_profiles": {
                "workflow_designer": {"provider": wd_provider, "config": _sanitize(wd_cfg)},
                "rl_coach": {"provider": rl_provider, "config": _sanitize(rl_cfg)},
            },
            "chat_history_dir": str(chat_history_dir),
            "messages": list(state.history),
        }
        write_chat_payload(path, payload)

    def _ensure_chat_file() -> None:
        """Create a temporary chat file name on first write."""
        if state.chat_path is not None:
            return
        ts = datetime.now().strftime("%y-%m-%d-%H%M%S")
        tmp = unique_path(chat_history_dir, f"chat_{ts}")
        state.chat_path = tmp
        _set_chat_title_from_path(tmp)
        _recent_menu_refresh_and_select(tmp.name)
        _persist_history()

    def _schedule_name_from_first_message(first_message: str) -> None:
        """
        Ask the LLM to suggest a short filename base (snake_case), then rename the chat file.
        Falls back to slugifying the first message if LLM is unavailable.
        """
        # Ensure we have a file to rename
        _ensure_chat_file()

        async def _run() -> None:
            base = ""
            try:
                profile = _assistant_profile_key(assistant_dd.value)
                provider = get_llm_provider(assistant=profile)
                cfg = get_llm_provider_config(assistant=profile)
                resp = await asyncio.to_thread(
                    lambda: suggest_chat_filename_base(
                        first_message=first_message,
                        provider=provider,
                        config=cfg,
                        timeout_s=OLLAMA_TIMEOUT_S,
                    )
                )
                base = slugify_filename(resp)
            except Exception:
                base = slugify_filename(first_message)

            try:
                old = state.chat_path
                if old is None:
                    return
                new_path = unique_path(chat_history_dir, base)
                if new_path != old:
                    old.rename(new_path)
                    state.chat_path = new_path
                    _set_chat_title_from_path(new_path)
                    _recent_menu_refresh_and_select(new_path.name)
                    _persist_history()
            except OSError:
                pass

        page.run_task(_run)

    def _toast_now(msg: str) -> None:
        async def _run_toast() -> None:
            await _toast(page, msg)

        page.run_task(_run_toast)

    def _row_builder(msg: dict[str, Any]) -> ft.Row:
        # bubble_width=None makes bubbles expand to available chat column width (responsive).
        return build_message_row(
            page=page,
            msg=msg,
            persist=_persist_history,
            toast=_toast_now,
            on_undo=on_undo,
            on_redo=on_redo,
            now_ts=_now_ts,
            bubble_width=None,
        )

    def _render_messages_from_history() -> None:
        render_messages(
            messages_col=messages_col,
            chat_title_txt=chat_title_txt,
            history=state.history,
            new_id=_new_id,
            now_ts=_now_ts,
            row_builder=_row_builder,
        )
        try:
            messages_col.update()
            page.update()
        except Exception:
            pass

    def _append(role: str, content: str, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        _ensure_chat_file()
        msg: dict[str, Any] = {"id": _new_id(), "ts": _now_ts(), "role": role, "content": content}
        if meta:
            msg.update(meta)
        state.history.append(msg)
        messages_col.controls.append(_row_builder(msg))
        try:
            messages_col.update()
            page.update()
        except Exception:
            pass
        _persist_history()
        return msg

    # In-progress assistant response row (UI-only; used for streaming).
    stream_row_ref: list[ft.Row | None] = [None]
    stream_txt_ref: list[ft.Text | None] = [None]

    def _clear_stream_row() -> None:
        row = stream_row_ref[0]
        if row is not None and row in messages_col.controls:
            messages_col.controls.remove(row)
            stream_row_ref[0] = None
            stream_txt_ref[0] = None
            safe_update(messages_col)
            safe_page_update(page)

    def _ensure_stream_row() -> ft.Text:
        if stream_txt_ref[0] is not None and stream_row_ref[0] is not None:
            return stream_txt_ref[0]  # type: ignore[return-value]

        txt = ft.Text("", size=12, color=ft.Colors.GREY_200, selectable=True, no_wrap=False)
        stream_txt_ref[0] = txt
        bubble = ft.Container(
            content=txt,
            padding=ft.padding.symmetric(horizontal=10, vertical=6),
            border_radius=8,
            bgcolor=ft.Colors.TRANSPARENT,
            expand=True,
        )
        # Align like assistant bubbles (left, with slight indent)
        row = ft.Row([ft.Container(expand=True, content=bubble, padding=ft.padding.only(left=12))])
        stream_row_ref[0] = row
        messages_col.controls.append(row)
        safe_update(messages_col)
        safe_page_update(page)
        return txt

    # Token that identifies the currently active LLM run.
    # When the user presses "Stop", we increment it to invalidate the in-flight run.
    run_token_ref: list[int] = [0]

    def _next_run_token() -> int:
        run_token_ref[0] += 1
        return run_token_ref[0]

    def _is_current_run(token: int) -> bool:
        return token == run_token_ref[0]

    # Inline status row shown below the most recent user message (UI-only; not persisted).
    status_inline_row_ref: list[ft.Row | None] = [None]
    status_inline_txt_ref: list[ft.Text | None] = [None]
    status_anim_token_ref: list[int] = [0]
    status_anim_base_ref: list[str | None] = [None]
    status_stop_btn_ref: list[ft.IconButton | None] = [None]

    def _set_inline_status(msg: str | None) -> None:
        # Clear
        if not msg:
            status_anim_token_ref[0] += 1
            status_anim_base_ref[0] = None
            row = status_inline_row_ref[0]
            if row is not None and row in messages_col.controls:
                messages_col.controls.remove(row)
                status_inline_row_ref[0] = None
                status_inline_txt_ref[0] = None
                status_stop_btn_ref[0] = None
                safe_update(messages_col)
                safe_page_update(page)
            return

        # Start / restart animation loop (token cancels any previous loop).
        status_anim_token_ref[0] += 1
        my_token = status_anim_token_ref[0]
        base = str(msg).strip()
        # If callers pass "Thinking…" / "Applying edit…", animate dots instead of a fixed ellipsis.
        base = base.rstrip(".").rstrip("…").rstrip()
        status_anim_base_ref[0] = base

        async def _animate() -> None:
            # 0..3 dots loop
            i = 0
            while True:
                if my_token != status_anim_token_ref[0]:
                    return
                txt = status_inline_txt_ref[0]
                b = status_anim_base_ref[0]
                if txt is None or not b:
                    return
                dots = "." * (i % 4)
                txt.value = f"{b}{dots}"
                safe_update(txt)
                safe_page_update(page)
                i += 1
                try:
                    await asyncio.sleep(0.35)
                except Exception:
                    return

        page.run_task(_animate)

        # Create if missing
        if status_inline_row_ref[0] is None or status_inline_txt_ref[0] is None:
            txt = ft.Text(f"{base}", size=11, color=ft.Colors.GREY_500, italic=True, no_wrap=False)
            status_inline_txt_ref[0] = txt

            def _stop(_e: ft.ControlEvent) -> None:
                if not state.busy:
                    return
                # Invalidate any in-flight run so late responses are ignored.
                _next_run_token()
                _set_inline_status(None)
                _clear_stream_row()
                _set_busy(False)
                focus_pref[0] = "bottom" if state.has_sent_any else "first"
                _schedule_restore_focus()

            bubble = ft.Container(
                content=txt,
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                border_radius=8,
                bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.WHITE),
                expand=True,
            )
            # Slight left indent to align with assistant replies
            stop_btn = ft.IconButton(
                icon=ft.Icons.STOP_CIRCLE,
                icon_size=16,
                tooltip="Stop",
                on_click=_stop,
                padding=0,
                visible=bool(state.busy),
                icon_color=ft.Colors.GREY_400,
            )
            status_stop_btn_ref[0] = stop_btn
            row = ft.Row(
                [
                    ft.Container(expand=True, content=bubble, padding=ft.padding.only(left=12)),
                    stop_btn,
                ],
                spacing=6,
            )
            status_inline_row_ref[0] = row
            messages_col.controls.append(row)
            safe_update(messages_col)
            safe_page_update(page)
            return

        # Update existing (base message; animation loop adds dots)
        status_inline_txt_ref[0].value = base
        safe_update(status_inline_txt_ref[0])
        safe_page_update(page)

    # --- Recent chat history picker (load/continue) ---
    def _load_chat_file(path: Path) -> None:
        if state.busy:
            return
        _set_inline_status(None)
        payload = load_chat_payload(path)
        if payload is None:
            async def _toast_load_fail() -> None:
                await _toast(page, "Could not load chat file")

            page.run_task(_toast_load_fail)
            return

        msgs = payload.get("messages")
        if not isinstance(msgs, list):
            msgs = []

        # Swap session to this chat
        state.chat_path = path
        _set_chat_title_from_path(path)
        state.session_id = str(payload.get("session_id") or _new_id())
        state.created_at = str(payload.get("created_at") or _now_ts())

        asst_sel = payload.get("assistant_selected")
        if asst_sel in ("Workflow Designer", "RL Coach"):
            assistant_dd.value = asst_sel
            try:
                assistant_dd.update()
            except Exception:
                pass

        state.history.clear()
        for m in msgs:
            if isinstance(m, dict):
                state.history.append(m)

        has_user = any(m.get("role") == "user" and (m.get("content") or "").strip() for m in state.history)
        state.has_sent_any = bool(has_user)
        top_input_container.visible = not state.has_sent_any
        bottom_input_row.visible = state.has_sent_any
        history_row_top.visible = not state.has_sent_any
        history_row_bottom.visible = state.has_sent_any
        chat_title_top_txt.visible = not state.has_sent_any
        chat_title_txt.visible = state.has_sent_any

        _render_messages_from_history()
        if recent_menu_ref[0] is not None:
            recent_menu_ref[0].set_selected(path.name)

        safe_update(
            top_input_container,
            bottom_input_row,
            history_row_top,
            history_row_bottom,
            chat_title_top_txt,
            chat_title_txt,
        )
        safe_page_update(page)

    recent_menu = RecentChatsMenu(page=page, chat_history_dir=chat_history_dir, on_select=_load_chat_file).build()
    recent_menu_ref[0] = recent_menu
    recent_menu.refresh()

    history_row_top = recent_menu.row_top
    history_row_bottom = recent_menu.row_bottom

    def _set_busy(v: bool) -> None:
        state.busy = v
        input_tf_first.disabled = v
        input_tf.disabled = v
        input_tf_first.update()
        input_tf.update()
        if not v:
            _set_inline_status(None)
            _clear_stream_row()
        # If the inline status row exists, toggle stop button visibility.
        if status_stop_btn_ref[0] is not None:
            try:
                status_stop_btn_ref[0].visible = bool(v)
                status_stop_btn_ref[0].update()
            except Exception:
                pass
        page.update()

    # Toggle input placement: top (first message) -> bottom (subsequent)
    top_input_container = ft.Container(content=input_tf_first, visible=True)
    bottom_input_row = ft.Row([input_tf], spacing=8, visible=False)

    def _after_first_send() -> None:
        if state.has_sent_any:
            return
        state.has_sent_any = True
        top_input_container.visible = False
        bottom_input_row.visible = True
        chat_title_top_txt.visible = False
        chat_title_txt.visible = True
        focus_pref[0] = "bottom"
        if recent_menu_ref[0] is not None:
            recent_menu_ref[0].set_phase(has_sent_any=True)
        safe_update(top_input_container, bottom_input_row, history_row_top, history_row_bottom, chat_title_top_txt, chat_title_txt)
        safe_page_update(page)

    def _send_from_field(field: ft.TextField) -> None:
        text = (field.value or "").strip()
        if not text or state.busy:
            return
        field.value = ""
        field.update()
        turn_id = _new_id()
        if not state.has_sent_any:
            _schedule_name_from_first_message(text)
        _append("user", text, meta={"turn_id": turn_id, "assistant": assistant_dd.value, "source": "user_submit"})
        token = _next_run_token()
        _set_inline_status("Thinking…")
        _after_first_send()
        _set_busy(True)

        async def _run() -> None:
            try:
                if not _is_current_run(token):
                    return
                asst: AssistantType = (assistant_dd.value or "Workflow Designer")  # type: ignore[assignment]
                profile = _assistant_profile_key(asst)
                provider = get_llm_provider(assistant=profile)
                cfg = get_llm_provider_config(assistant=profile)
                options = {"temperature": 0.3, "num_predict": OLLAMA_NUM_PREDICT}

                if asst == "Workflow Designer":
                    ctx = json.dumps(_graph_summary(graph_ref[0]), indent=2)
                    user_with_ctx = f"Current process graph (summary):\n{ctx}\n\nUser request: {text}"
                    msgs: list[dict[str, str]] = [{"role": "system", "content": WORKFLOW_DESIGNER_SYSTEM}]
                    msgs.extend(_messages_from_history(state.history))
                    msgs.append({"role": "user", "content": user_with_ctx})

                    # Stream response pieces into a UI-only bubble while generating.
                    q: asyncio.Queue[Any] = asyncio.Queue()
                    loop = asyncio.get_running_loop()

                    def _producer() -> None:
                        try:
                            for piece in llm_client.chat_stream(
                                provider=provider,
                                config=cfg,
                                messages=msgs,
                                timeout_s=OLLAMA_TIMEOUT_S,
                                options=options,
                            ):
                                if not _is_current_run(token):
                                    break
                                loop.call_soon_threadsafe(q.put_nowait, piece)
                        except Exception as ex:
                            loop.call_soon_threadsafe(q.put_nowait, ex)
                        finally:
                            loop.call_soon_threadsafe(q.put_nowait, None)

                    Thread(target=_producer, daemon=True).start()

                    content_parts: list[str] = []
                    wrote_any = False
                    stream_txt = _ensure_stream_row()

                    while True:
                        item = await q.get()
                        if item is None:
                            break
                        if isinstance(item, Exception):
                            raise item
                        if not _is_current_run(token):
                            return
                        piece = str(item)
                        if piece:
                            content_parts.append(piece)
                            if not wrote_any:
                                wrote_any = True
                                _set_inline_status("Writing…")
                            stream_txt.value = "".join(content_parts)
                            safe_update(stream_txt)
                            safe_page_update(page)

                    content = "".join(content_parts).strip()
                    if not _is_current_run(token):
                        return
                    if not content:
                        content = "(No response from model.)"
                    _clear_stream_row()
                    
                    # Normalize edits
                    parsed_blocks = _parse_all_json_blocks(content)

                    edits: list[dict[str, Any]] = []

                    for parsed in parsed_blocks:
                        if isinstance(parsed, list):
                            edits.extend([e for e in parsed if isinstance(e, dict)])

                        elif isinstance(parsed, dict):
                            if parsed.get("action"):
                                edits.append(parsed)

                            elif isinstance(parsed.get("edits"), list):
                                edits.extend(
                                    [e for e in parsed["edits"] if isinstance(e, dict)]
                                )

                    apply_result: dict[str, Any] = {
                        "attempted": False,
                        "success": None,
                        "error": None,
                    }

                    # Apply all edits sequentially
                    if edits:
                        apply_result["attempted"] = True
                        _set_inline_status("Applying edits…")

                        current_graph = graph_ref[0] or {"units": [], "connections": []}

                        try:
                            for edit in edits:
                                if not _is_current_run(token):
                                    return

                                if not isinstance(edit, dict):
                                    continue

                                if edit.get("action") in (None, "no_edit"):
                                    continue

                                current_graph = process_assistant_apply(current_graph, edit)

                            set_graph(current_graph)
                            apply_result["success"] = True
                            await _toast(page, "Applied")

                        except Exception as ex:
                            apply_result["success"] = False
                            apply_result["error"] = str(ex)[:500]
                            await _toast(page, f"Could not apply edits: {str(ex)[:120]}")


                    if not _is_current_run(token):
                        return
                    _set_inline_status(None)
                    _append(
                        "assistant",
                        content,
                        meta={
                            "turn_id": turn_id,
                            "assistant": asst,
                            "source": "assistant_response",
                            "llm_request": {
                                "provider": provider,
                                "config": cfg,
                                "timeout_s": OLLAMA_TIMEOUT_S,
                                "options": options,
                                "messages": msgs,
                            },
                            "llm_response": {"raw": content},
                            "parsed_edits": edits,
                            "apply": apply_result,
                        },
                    )
                    return

                # RL Coach: training config not yet wired in Flet; still allow chat response without applying.
                msgs = [{"role": "system", "content": RL_COACH_SYSTEM}]
                msgs.extend(_messages_from_history(state.history))
                msgs.append({"role": "user", "content": text})

                q2: asyncio.Queue[Any] = asyncio.Queue()
                loop2 = asyncio.get_running_loop()

                def _producer2() -> None:
                    try:
                        for piece in llm_client.chat_stream(
                            provider=provider,
                            config=cfg,
                            messages=msgs,
                            timeout_s=OLLAMA_TIMEOUT_S,
                            options=options,
                        ):
                            if not _is_current_run(token):
                                break
                            loop2.call_soon_threadsafe(q2.put_nowait, piece)
                    except Exception as ex:
                        loop2.call_soon_threadsafe(q2.put_nowait, ex)
                    finally:
                        loop2.call_soon_threadsafe(q2.put_nowait, None)

                Thread(target=_producer2, daemon=True).start()

                parts2: list[str] = []
                wrote_any2 = False
                stream_txt2 = _ensure_stream_row()

                while True:
                    item = await q2.get()
                    if item is None:
                        break
                    if isinstance(item, Exception):
                        raise item
                    if not _is_current_run(token):
                        return
                    piece = str(item)
                    if piece:
                        parts2.append(piece)
                        if not wrote_any2:
                            wrote_any2 = True
                            _set_inline_status("Writing…")
                        stream_txt2.value = "".join(parts2)
                        safe_update(stream_txt2)
                        safe_page_update(page)

                content = "".join(parts2).strip()
                if not _is_current_run(token):
                    return
                raw = content or "(No response from model.)"
                _clear_stream_row()
                _set_inline_status(None)
                _append(
                    "assistant",
                    raw,
                    meta={
                        "turn_id": turn_id,
                        "assistant": asst,
                        "source": "assistant_response",
                        "llm_request": {
                            "provider": provider,
                            "config": cfg,
                            "timeout_s": OLLAMA_TIMEOUT_S,
                            "options": options,
                            "messages": msgs,
                        },
                        "llm_response": {"raw": raw},
                    },
                )
                await _toast(page, "RL Coach reply (not applied in Flet yet)")
            except ImportError as ex:
                if not _is_current_run(token):
                    return
                _set_inline_status(None)
                _append(
                    "assistant",
                    str(ex),
                    meta={"turn_id": turn_id, "assistant": assistant_dd.value, "source": "error", "error_type": "ImportError"},
                )
            except Exception as ex:
                # Try to present nicer Ollama errors
                if not _is_current_run(token):
                    return
                _set_inline_status(None)
                _append(
                    "assistant",
                    llm_client.format_exception(provider=provider if "provider" in locals() else "ollama", e=ex),
                    meta={"turn_id": turn_id, "assistant": assistant_dd.value, "source": "error", "error_type": type(ex).__name__},
                )
            finally:
                if _is_current_run(token):
                    _set_inline_status(None)
                    _clear_stream_row()
                    _set_busy(False)

        page.run_task(_run)

    input_tf_first.on_submit = lambda _e: _send_from_field(input_tf_first)
    input_tf.on_submit = lambda _e: _send_from_field(input_tf)

    def _reset_chat_ui() -> None:
        # Reset state
        state.history.clear()
        state.busy = False
        state.has_sent_any = False
        state.chat_path = None
        state.session_id = _new_id()
        state.created_at = _now_ts()

        # Reset inputs
        input_tf_first.value = ""
        input_tf.value = ""
        input_tf_first.disabled = False
        input_tf.disabled = False

        # Reset layout (top composer visible again)
        top_input_container.visible = True
        bottom_input_row.visible = False
        chat_title_top_txt.visible = True
        chat_title_txt.visible = False
        if recent_menu_ref[0] is not None:
            recent_menu_ref[0].set_phase(has_sent_any=False)

        # Reset title
        _set_chat_title("new_chat")

        # Reset messages column (keep title at top)
        _set_inline_status(None)
        messages_col.controls = [chat_title_txt]

        # Reset history picker
        _recent_menu_refresh_and_select(None)

        safe_update(
            messages_col,
            top_input_container,
            bottom_input_row,
            history_row_top,
            history_row_bottom,
            chat_title_top_txt,
            chat_title_txt,
            input_tf_first,
            input_tf,
        )
        safe_page_update(page)

    def _start_new_chat(_e: ft.ControlEvent) -> None:
        if state.busy:
            return
        _reset_chat_ui()

        # Try to force focus into the first-message input.
        # Some platforms/builds won't honor focus() immediately after a click,
        # so we also toggle autofocus briefly.
        try:
            input_tf_first.can_request_focus = True
        except Exception:
            pass
        try:
            input_tf_first.autofocus = True
            safe_update(input_tf_first)
            safe_page_update(page)
        except Exception:
            pass

        # Put cursor into the first-message input for fast typing.
        async def _focus_first() -> None:
            # Some Flet builds need a small delay (and sometimes a retry)
            # after visibility/layout changes before focus "sticks".
            for delay_s in (0.0, 0.05, 0.2, 0.5):
                try:
                    await asyncio.sleep(delay_s)
                    await input_tf_first.focus()
                    # Turn off autofocus after we succeed.
                    try:
                        input_tf_first.autofocus = False
                        safe_update(input_tf_first)
                    except Exception:
                        pass
                    return
                except Exception:
                    continue

        page.run_task(_focus_first)
        focus_pref[0] = "first"

    # Populate recent chats on first render
    recent_menu.refresh()

    return ft.Column(
        [
            ft.Row(
                [
                    ft.Icon(ft.Icons.SMART_TOY, size=30, color=ft.Colors.GREY_200),
                    ft.Container(expand=True),
                    ft.IconButton(
                        icon=ft.Icons.ADD,
                        icon_size=18,
                        tooltip="New chat",
                        on_click=_start_new_chat,
                    ),
                    assistant_dd,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            chat_title_top_txt,
            top_input_container,
            history_row_top,
            ft.Container(content=messages_col, expand=True),
            bottom_input_row,
            history_row_bottom,
        ],
        expand=True,
        spacing=8,
    )

