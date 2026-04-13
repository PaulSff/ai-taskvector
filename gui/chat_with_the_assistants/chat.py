"""
Flet assistants chat panel: main roles come from ``assistants.roles.list_chat_dropdown_role_ids()`` (see each
``role.yaml`` ``chat:`` block). Chat always runs a workflow per assistant (no direct LLM path).

Turn routing uses ``role_id`` (snake_case), e.g. ``workflow_designer`` / ``rl_coach``, not hardcoded display strings.
"""
from __future__ import annotations

import asyncio
import os
import queue
import sys
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from collections.abc import Coroutine
from typing import Any, Callable

import flet as ft

from runtime.stream_ui_signals import CHAMELEON_STREAM_PREFIX, INLINE_STATUS_PREFIX

from gui.chat_with_the_assistants.chat_turn_context import normalize_user_message_for_workflow
from gui.chat_with_the_assistants.create_filename import run_create_filename_workflow
from assistants.roles import (
    RL_COACH_ROLE_ID,
    WORKFLOW_DESIGNER_ROLE_ID,
    get_role,
    list_chat_dropdown_role_ids,
    role_chat_feature_enabled,
)
from gui.components.workflow.process_graph import ProcessGraph

from gui.components.settings import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    get_chat_stream_ui_interval_ms,
    get_coding_is_allowed,
    get_chat_history_dir,
    get_llm_provider,
    get_llm_provider_config,
    get_mydata_dir,
    get_training_config_path,
    get_rag_embedding_model,
    get_rag_index_dir,
)
from gui.utils.notifications import show_toast

from gui.chat_with_the_assistants.chat_persistence import (
    build_chat_payload,
    message_for_persist,
    suggest_initial_chat_path,
)
from gui.chat_with_the_assistants.history_store import (
    append_chat_message_delta,
    load_chat_payload,
    slugify_filename,
    unique_path,
    write_chat_payload,
)
from gui.chat_with_the_assistants.language_control import parse_session_language_command
from gui.chat_with_the_assistants.load_chat_history import load_chat_session
from gui.chat_with_the_assistants.message_renderer import (
    build_assistant_streaming_body,
    build_message_row,
    render_messages,
    streaming_assistant_opened_code_fence,
)
from gui.chat_with_the_assistants.recent_chats_menu import RecentChatsMenu
from gui.chat_with_the_assistants.status_bar import StatusBarController
from gui.chat_with_the_assistants.state import ChatSessionState
from gui.chat_with_the_assistants.ui_utils import safe_page_update, safe_update
from gui.chat_with_the_assistants.graph_references import GraphReferencesController
from gui.chat_with_the_assistants.chat_layout import (
    build_chat_composer,
    build_chat_inner_column,
    build_history_row_with_model,
)
from gui.chat_with_the_assistants.focus_handler import ChatFocusHandler
from gui.components.rag_tab import run_rag_file_pick_copy_and_index
from gui.chat_with_the_assistants.role_handlers.context import RoleChatTurnContext
from gui.chat_with_the_assistants.role_handlers.registry import get_role_chat_handler

CHAT_GRAPH_DRAG_GROUP = "chat_graph_ref"


AssistantDisplay = str  # role display_name from dropdown (see list_chat_dropdown_role_ids)

CHAT_HISTORY_SCHEMA_VERSION = 3
CHAT_AUTOSAVE_DEBOUNCE_S = 0.45


def _workflow_debug_log_enabled() -> bool:
    return (os.environ.get("WORKFLOW_DEBUG_LOG") or "").strip() == "1"


def _workflow_debug_log(msg: str) -> None:
    if _workflow_debug_log_enabled():
        print(f"[workflow_debug] {msg}", file=sys.stderr, flush=True)

def _now_ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid4().hex


async def _toast(page: ft.Page, msg: str) -> None:
    await show_toast(page, msg)


def build_assistants_chat_panel(
    page: ft.Page,
    *,
    graph_ref: list[ProcessGraph | None],
    set_graph: Callable[[ProcessGraph | None], None],
    apply_from_assistant: Callable[[ProcessGraph | None], None] | None = None,
    get_recent_changes: Callable[[], str | None] | None = None,
    on_undo: Callable[[], None] | None = None,
    on_redo: Callable[[], None] | None = None,
    show_run_current_graph: bool = False,
    on_show_run_console: Callable[[dict], None] | None = None,
    chat_panel_api: dict[str, Any] | None = None,
) -> ft.Control:
    """
    Build the right-column assistants chat panel.
    Applies Workflow Designer edits to the current graph.
    """
    _dropdown_role_ids = list_chat_dropdown_role_ids()
    if not _dropdown_role_ids:
        _dropdown_role_ids = (WORKFLOW_DESIGNER_ROLE_ID, RL_COACH_ROLE_ID)
    _chat_assistant_display_by_role = {rid: get_role(rid).display_name for rid in _dropdown_role_ids}
    _chat_role_by_display = {get_role(rid).display_name: rid for rid in _dropdown_role_ids}
    _chat_display_names = frozenset(_chat_role_by_display.keys())
    _default_chat_display = _chat_assistant_display_by_role[_dropdown_role_ids[0]]

    assistant_dd = ft.Dropdown(
        label="Assistant",
        value=_default_chat_display,
        width=190,
        height=36,
        text_style=ft.TextStyle(size=12),
        options=[ft.dropdown.Option(_chat_assistant_display_by_role[rid]) for rid in _dropdown_role_ids],
    )

    def _assistant_profile_key(v: str | None) -> str:
        label = (v or "").strip()
        return _chat_role_by_display.get(label, _dropdown_role_ids[0])

    state = ChatSessionState(
        history=[],
        busy=False,
        has_sent_any=False,
        session_id=_new_id(),
        created_at=_now_ts(),
        chat_path=None,
        session_language="",
    )
    _workflow_debug_log("enabled=1 (chat panel initialized)")

    # Stores last workflow apply result for grounding
    last_apply_result_ref: list[dict[str, Any] | None] = [None]

    # Pending graph/code references (chips); prepended to next user send.
    def _resolve_unit_meta(uid: str) -> tuple[str, str]:
        g = graph_ref[0]
        label = uid
        unit_type = ""
        if g is not None:
            u = g.get_unit(uid)
            if u is not None:
                label = ((getattr(u, "name", None) or "") or "").strip() or uid
                unit_type = (getattr(u, "type", None) or "") or ""
        return (label, unit_type)

    first_composer = build_chat_composer(
        min_lines=4,
        max_lines=12,
        on_stop_click=lambda _e: _on_stop(),
        on_upload_click=lambda _e: page.run_task(run_rag_file_pick_copy_and_index, page),
    )
    bottom_composer = build_chat_composer(
        min_lines=2,
        max_lines=6,
        on_stop_click=lambda _e: _on_stop(),
        on_upload_click=lambda _e: page.run_task(run_rag_file_pick_copy_and_index, page),
    )
    input_tf_first = first_composer.input_tf
    stop_btn_first = first_composer.stop_btn
    upload_btn_first = first_composer.upload_btn
    stacked_first = first_composer.container
    input_tf = bottom_composer.input_tf
    stop_btn_bottom = bottom_composer.stop_btn
    upload_btn_bottom = bottom_composer.upload_btn
    stacked_bottom = bottom_composer.container
    focus_handler = ChatFocusHandler(
        page=page,
        first_field=input_tf_first,
        bottom_field=input_tf,
        is_busy=lambda: state.busy,
    )

    # Some Flet versions don't accept on_* in constructor; assign after creation.
    input_tf_first.on_focus = lambda _e: focus_handler.mark_first()
    input_tf.on_focus = lambda _e: focus_handler.mark_bottom()
    focus_handler.install_resize_restore()

    # --- Chat history persistence (auto-save) ---
    chat_history_dir = get_chat_history_dir()
    chat_history_dir.mkdir(parents=True, exist_ok=True)
    stream_ui_min_interval_s = max(0.016, float(get_chat_stream_ui_interval_ms()) / 1000.0)

    # Chat title.
    # Before first message: show above the first-message composer.
    # After first message: show at top of messages scroll area.
    chat_title_top_txt = ft.Text("new_chat", size=12, color=ft.Colors.GREY_500, visible=True)
    chat_title_txt = ft.Text("new_chat", size=12, color=ft.Colors.GREY_500, visible=False)

    messages_col = ft.Column(
        [chat_title_txt],
        scroll=ft.ScrollMode.AUTO,
        auto_scroll=False,  # required for scroll_to(); we scroll during streaming explicitly
        expand=True,
        spacing=8,
    )

    async def _scroll_chat_to_bottom() -> None:
        """Keep the message list pinned to the bottom while the assistant streams tokens."""
        try:
            await messages_col.scroll_to(offset=-1, duration=0)
        except Exception:
            pass

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
        if state.chat_path is None:
            return
        payload = build_chat_payload(
            schema_version=CHAT_HISTORY_SCHEMA_VERSION,
            session_id=state.session_id,
            created_at=state.created_at,
            assistant_selected=assistant_dd.value,
            session_language=state.session_language,
            chat_history_dir=chat_history_dir,
            messages=state.history,
            get_llm_provider=lambda a: get_llm_provider(assistant=a),
            get_llm_provider_config=lambda a: get_llm_provider_config(assistant=a) or {},
        )
        write_chat_payload(state.chat_path, payload)

    # Debounced autosave for chat-heavy paths; keeps disk writes bounded as history grows.
    _persist_token_ref: list[int] = [0]

    def _persist_history_debounced(delay_s: float = CHAT_AUTOSAVE_DEBOUNCE_S) -> None:
        _persist_token_ref[0] += 1
        my_token = _persist_token_ref[0]

        async def _run() -> None:
            try:
                await asyncio.sleep(max(0.0, delay_s))
            except Exception:
                return
            if my_token != _persist_token_ref[0]:
                return
            _persist_history()

        page.run_task(_run)

    def _schedule_name_from_first_message(first_message: str) -> None:
        """
        Run create_filename workflow to suggest a short filename base (snake_case), then rename the chat file.
        Falls back to slugifying the first message if the workflow fails.

        Expects ``state.chat_path`` to already be set (first user row appended via :func:`_append`).
        """
        if state.chat_path is None:
            return

        async def _run() -> None:
            base = ""
            profile = _assistant_profile_key(assistant_dd.value)
            use_title_wf = True
            try:
                use_title_wf = role_chat_feature_enabled(get_role(profile).chat, "create_chat_title", default=True)
            except Exception:
                use_title_wf = True
            if use_title_wf:
                try:
                    provider = get_llm_provider(assistant=profile)
                    cfg = get_llm_provider_config(assistant=profile)
                    resp = await asyncio.to_thread(
                        run_create_filename_workflow,
                        first_message,
                        provider,
                        cfg,
                        60.0,
                    )
                    base = slugify_filename(resp) if resp else slugify_filename(first_message)
                except Exception:
                    base = slugify_filename(first_message)
            else:
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

    refs_controller = GraphReferencesController(
        new_id=_new_id,
        toast=_toast_now,
        resolve_unit_meta=_resolve_unit_meta,
    )
    refs_chips_row = refs_controller.row

    def _row_builder(msg: dict[str, Any]) -> ft.Row:
        # bubble_width=None makes bubbles expand to available chat column width (responsive).
        return build_message_row(
            page=page,
            msg=msg,
            persist=_persist_history_debounced,
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
        page.run_task(_scroll_chat_to_bottom)

    def _append(
        role: str,
        content: str,
        *,
        meta: dict[str, Any] | None = None,
        after_io: Callable[[], Coroutine[Any, Any, None]] | None = None,
        skip_messages_col_update: bool = False,
    ) -> dict[str, Any]:
        """
        Insert a message row and update the list control only (sync). After ``asyncio.sleep(0)``:
        assign path if needed, write delta, scroll, then optional ``after_io`` (e.g. assistant run).
        On the first message of a new chat file, recent-menu refresh + full JSON snapshot run in a
        separate task so they do not delay ``after_io`` (matches responsiveness of later messages).
        """
        was_new_file = state.chat_path is None
        msg: dict[str, Any] = {"id": _new_id(), "ts": _now_ts(), "role": role, "content": content}
        if meta:
            msg.update(meta)
        state.history.append(msg)
        row = _row_builder(msg)
        msg["_flet_row"] = row
        # Keep chronological order: new messages below previous. If the stream row is present,
        # insert this message before it so it appears above the (streaming) bubble, not below.
        stream_row = stream_row_ref[0]
        if stream_row is not None and stream_row in messages_col.controls:
            idx = messages_col.controls.index(stream_row)
            messages_col.controls.insert(idx, row)
        else:
            messages_col.controls.append(row)
        if not skip_messages_col_update:
            safe_update(messages_col)

        async def _flush_append_io() -> None:
            await asyncio.sleep(0)
            if state.chat_path is None:
                tmp = suggest_initial_chat_path(chat_history_dir)
                state.chat_path = tmp
                _set_chat_title_from_path(tmp)
            if state.chat_path is not None:
                append_chat_message_delta(state.chat_path, message_for_persist(msg))
            await _scroll_chat_to_bottom()
            # First message only: menu rebuild + full snapshot are slow; run them concurrently with
            # after_io (planning status, composer switch, assistant) instead of blocking responsiveness.
            if was_new_file and state.chat_path is not None:

                async def _menu_refresh_and_snapshot() -> None:
                    await asyncio.sleep(0)
                    if state.chat_path is None:
                        return
                    _recent_menu_refresh_and_select(state.chat_path.name)
                    _persist_history()

                page.run_task(_menu_refresh_and_snapshot)

            if after_io is not None:
                await after_io()

        page.run_task(_flush_append_io)
        return msg

    def _replace_assistant_message_row(msg: dict[str, Any]) -> None:
        """
        Rebuild the Flet row after msg['content'] was updated in place (e.g. merged post-apply reply).
        Second-turn streaming is cleared in finally; without this, that text disappears from the chat bubble.
        """
        if (msg.get("role") or "").strip().lower() != "assistant":
            return
        try:
            old_row = msg.get("_flet_row")
            new_row = _row_builder(msg)
            msg["_flet_row"] = new_row
            if old_row is not None and old_row in messages_col.controls:
                idx = messages_col.controls.index(old_row)
                messages_col.controls[idx] = new_row
            else:
                return
            safe_update(messages_col)
            safe_page_update(page)
            page.run_task(_scroll_chat_to_bottom)
            _persist_history_debounced()
        except Exception:
            pass

    # In-progress assistant response row (UI-only; used for streaming).
    stream_row_ref: list[ft.Row | None] = [None]
    stream_bubble_ref: list[ft.Container | None] = [None]
    stream_plain_txt_ref: list[ft.Text | None] = [None]
    stream_buffer_ref: list[str] = [""]
    stream_rich_ref: list[bool] = [False]

    def _clear_stream_row() -> None:
        row = stream_row_ref[0]
        if row is not None and row in messages_col.controls:
            messages_col.controls.remove(row)
            stream_row_ref[0] = None
            stream_bubble_ref[0] = None
            stream_plain_txt_ref[0] = None
            stream_buffer_ref[0] = ""
            stream_rich_ref[0] = False
            safe_update(messages_col)
            safe_page_update(page)

    def _ensure_stream_row() -> None:
        if stream_row_ref[0] is not None:
            return

        txt = ft.Text("", size=12, color=ft.Colors.GREY_200, selectable=True, no_wrap=False)
        stream_plain_txt_ref[0] = txt
        bubble = ft.Container(
            content=txt,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border_radius=8,
            bgcolor=ft.Colors.TRANSPARENT,
            expand=True,
        )
        stream_bubble_ref[0] = bubble
        # Align like assistant bubbles (left, with slight indent)
        row = ft.Row([ft.Container(expand=True, content=bubble, padding=ft.Padding.only(left=12))])
        stream_row_ref[0] = row
        messages_col.controls.append(row)
        safe_update(messages_col)
        safe_page_update(page)
        page.run_task(_scroll_chat_to_bottom)

    def _prepare_stream_row() -> None:
        """Show the streaming bubble before the model runs, so tokens appear as they generate."""
        _ensure_stream_row()
        stream_buffer_ref[0] = ""
        stream_rich_ref[0] = False
        b = stream_bubble_ref[0]
        t = stream_plain_txt_ref[0]
        if b is not None and t is not None:
            b.content = t
            t.value = ""
            safe_update(t)
            safe_update(b)
        safe_page_update(page)
        page.run_task(_scroll_chat_to_bottom)

    async def _run_workflow_with_streaming(
        run_fn: Callable[..., Any],
        *args: Any,
        _run_token: int | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run a workflow in a thread while an async consumer on the main thread updates the stream row from a queue. This way streamed tokens are visible during generation (page.run_task from the executor thread does not run until the main thread finishes awaiting the thread)."""
        stream_queue: queue.Queue[str | None] = queue.Queue()
        stream_cb = stream_queue.put

        def run_in_thread() -> Any:
            result = run_fn(*args, **kwargs, stream_callback=stream_cb)
            stream_queue.put(None)  # sentinel so consumer exits
            return result

        async def stream_consumer() -> None:
            last_paint_ts = 0.0

            async def _flush_stream(force: bool = False) -> None:
                nonlocal last_paint_ts
                if _run_token is not None and (not _is_current_run(_run_token)):
                    return
                now = time.perf_counter()
                if (not force) and (now - last_paint_ts < stream_ui_min_interval_s):
                    return
                _ensure_stream_row()
                text = stream_buffer_ref[0]
                b = stream_bubble_ref[0]
                t = stream_plain_txt_ref[0]
                if b is None or t is None:
                    return
                if not stream_rich_ref[0] and streaming_assistant_opened_code_fence(text):
                    stream_rich_ref[0] = True
                if stream_rich_ref[0]:
                    b.content = build_assistant_streaming_body(
                        page=page,
                        toast=_toast_now,
                        on_undo=on_undo,
                        on_redo=on_redo,
                        content=text,
                        bubble_width=None,
                    )
                    safe_update(b)
                else:
                    t.value = text
                    safe_update(t)
                safe_page_update(page)
                await _scroll_chat_to_bottom()
                _set_inline_status(None)
                last_paint_ts = now

            while True:
                piece = await asyncio.get_event_loop().run_in_executor(None, stream_queue.get)
                if piece is None:
                    await _flush_stream(force=True)
                    break
                if _run_token is not None and (not _is_current_run(_run_token)):
                    # Stop was clicked (or a newer run superseded this one): drain queue without UI updates.
                    continue
                if piece.startswith(INLINE_STATUS_PREFIX):
                    rest = piece[len(INLINE_STATUS_PREFIX) :]
                    _set_inline_status(rest if rest else None)
                    safe_page_update(page)
                    continue
                if piece.startswith(CHAMELEON_STREAM_PREFIX):
                    # Chameleon ``stream_outputs`` JSON payloads share the queue with tokens; do not show as text.
                    continue
                stream_buffer_ref[0] += piece
                await _flush_stream(force=False)

        _, response = await asyncio.gather(stream_consumer(), asyncio.to_thread(run_in_thread))
        return response

    # Token that identifies the currently active LLM run.
    run_token_ref: list[int] = [0]

    def _next_run_token() -> int:
        run_token_ref[0] += 1
        return run_token_ref[0]

    def _is_current_run(token: int) -> bool:
        return token == run_token_ref[0]

    def _on_stop() -> None:
        if not state.busy:
            return
        _next_run_token()
        status_bar.set_status(None)
        _clear_stream_row()
        _set_busy(False)
        focus_handler.set_preference("bottom" if state.has_sent_any else "first")
        focus_handler.schedule_restore()

    status_bar = StatusBarController(
        page=page,
        messages_col=messages_col,
        safe_update=safe_update,
        safe_page_update=safe_page_update,
    )

    def _set_inline_status(msg: str | None, *, flush: bool = True) -> None:
        status_bar.set_status(msg, flush=flush)

    # --- Recent chat history picker (load/continue) ---
    def _load_chat_file(path: Path) -> None:
        if state.busy:
            return
        _set_inline_status(None)
        session = load_chat_session(
            path,
            load_payload=load_chat_payload,
            new_id=_new_id,
            now_ts=_now_ts,
        )
        if session is None:
            async def _toast_load_fail() -> None:
                await _toast(page, "Could not load chat file")

            page.run_task(_toast_load_fail)
            return

        state.chat_path = path
        _set_chat_title_from_path(path)
        state.session_id = session["session_id"]
        state.created_at = session["created_at"]
        state.session_language = str(session.get("session_language") or "").strip()
        _workflow_debug_log(f"loaded session_language={state.session_language}")

        asst_sel = session.get("assistant_selected")
        if asst_sel in _chat_display_names:
            assistant_dd.value = asst_sel
            try:
                assistant_dd.update()
            except Exception:
                pass

        state.history.clear()
        for m in session["messages"]:
            if isinstance(m, dict):
                state.history.append(m)
        state.has_sent_any = session["has_sent_any"]

        top_input_container.visible = not state.has_sent_any
        bottom_input_row.visible = state.has_sent_any
        history_row_top.visible = not state.has_sent_any
        history_row_bottom.visible = state.has_sent_any
        chat_title_top_txt.visible = not state.has_sent_any
        chat_title_txt.visible = state.has_sent_any
        if wrapper_row_ref and wrapper_row_ref[0] is not None:
            wrapper_row_ref[0].visible = state.has_sent_any
        if top_wrapper_row_ref and top_wrapper_row_ref[0] is not None:
            top_wrapper_row_ref[0].visible = not state.has_sent_any

        _render_messages_from_history()
        if recent_menu_ref[0] is not None:
            recent_menu_ref[0].set_selected(path.name)

        safe_update(
            top_input_container,
            bottom_input_row,
            history_row_top_with_model,
            history_row_with_model,
            chat_title_top_txt,
            chat_title_txt,
        )
        safe_page_update(page)

    recent_menu = RecentChatsMenu(page=page, chat_history_dir=chat_history_dir, on_select=_load_chat_file).build()
    recent_menu_ref[0] = recent_menu
    recent_menu.refresh()

    history_row_top = recent_menu.row_top
    history_row_bottom = recent_menu.row_bottom

    # Model name from settings (shown to the right of the chat history dropdown in both first-message and bottom layout)
    model_label = ft.Text("", size=11, color=ft.Colors.GREY_400)
    model_label_top = ft.Text("", size=11, color=ft.Colors.GREY_400)

    def _update_model_label() -> None:
        profile = _assistant_profile_key(assistant_dd.value)
        cfg = get_llm_provider_config(assistant=profile)
        value = str(cfg.get("model") or "—").strip()
        model_label.value = value
        model_label_top.value = value
        try:
            model_label.update()
            model_label_top.update()
        except Exception:
            pass

    _update_model_label()
    wrapper_row_ref: list[ft.Row | None] = [None]
    top_wrapper_row_ref: list[ft.Row | None] = [None]
    history_row_top_with_model = build_history_row_with_model(
        history_row_top, model_label_top, visible=history_row_top.visible
    )
    top_wrapper_row_ref[0] = history_row_top_with_model
    history_row_with_model = build_history_row_with_model(
        history_row_bottom, model_label, visible=history_row_bottom.visible
    )
    wrapper_row_ref[0] = history_row_with_model

    _original_set_phase = recent_menu.set_phase

    def _set_phase_patched(has_sent_any: bool) -> None:
        _original_set_phase(has_sent_any=has_sent_any)
        if wrapper_row_ref[0] is not None:
            wrapper_row_ref[0].visible = has_sent_any
            safe_update(wrapper_row_ref[0])
        if top_wrapper_row_ref[0] is not None:
            top_wrapper_row_ref[0].visible = not has_sent_any
            safe_update(top_wrapper_row_ref[0])
        safe_page_update(page)

    recent_menu.set_phase = _set_phase_patched

    def _set_busy(v: bool) -> None:
        state.busy = v
        input_tf_first.disabled = v
        input_tf.disabled = v
        stop_btn_first.visible = bool(v)
        stop_btn_bottom.visible = bool(v)
        upload_btn_first.disabled = v
        upload_btn_bottom.disabled = v
        if show_run_current_graph:
            run_current_graph_cb.disabled = v
        if not v:
            _set_inline_status(None)
            _clear_stream_row()
        safe_update(
            input_tf_first,
            input_tf,
            stop_btn_first,
            stop_btn_bottom,
            upload_btn_first,
            upload_btn_bottom,
            run_current_graph_cb if show_run_current_graph else None,
        )

    # Toggle input placement: top (first message) -> bottom (subsequent)
    top_input_container = ft.Container(content=stacked_first, visible=True)
    run_current_graph_cb = ft.Checkbox(label="Run current graph", value=False, tooltip="(-dev) Execute the current workflow with this message instead of assistant_workflow.json")
    bottom_input_row_controls: list[ft.Control] = [stacked_bottom]
    if show_run_current_graph:
        bottom_input_row_controls.append(run_current_graph_cb)
    bottom_input_row = ft.Row(bottom_input_row_controls, spacing=8, visible=False)

    def _run_current_graph_effective(profile: str) -> bool:
        if not show_run_current_graph:
            return False
        try:
            return role_chat_feature_enabled(get_role(profile).chat, "graph_canvas", default=True)
        except Exception:
            return True

    def _update_run_current_graph_visibility() -> None:
        if not show_run_current_graph:
            return
        try:
            vis = _run_current_graph_effective(_assistant_profile_key(assistant_dd.value))
        except Exception:
            vis = True
        run_current_graph_cb.visible = vis
        if not vis:
            run_current_graph_cb.value = False
        try:
            run_current_graph_cb.update()
        except Exception:
            pass

    def _on_assistant_dd_change(_e: ft.ControlEvent | None) -> None:
        _update_model_label()
        _update_run_current_graph_visibility()

    assistant_dd.on_change = _on_assistant_dd_change
    _update_run_current_graph_visibility()

    def _after_first_send() -> None:
        if state.has_sent_any:
            return
        state.has_sent_any = True
        top_input_container.visible = False
        bottom_input_row.visible = True
        chat_title_top_txt.visible = False
        chat_title_txt.visible = True
        focus_handler.set_preference("bottom")
        if recent_menu_ref[0] is not None:
            recent_menu_ref[0].set_phase(has_sent_any=True)
        safe_update(top_input_container, bottom_input_row, history_row_top_with_model, history_row_with_model, chat_title_top_txt, chat_title_txt)
        safe_page_update(page)

    # Hoisted out of _send_from_field so Enter does not synchronously re-parse a ~500-line nested def
    # before the handler returns (that delay blocked the status line from painting).
    async def _run_chat_turn(token: int, *, turn_id: str, message_for_workflow: str) -> None:
        try:
            if not _is_current_run(token):
                return
            asst: AssistantDisplay = (assistant_dd.value or _default_chat_display)
            profile = _assistant_profile_key(asst)
            provider = get_llm_provider(assistant=profile)
            cfg = get_llm_provider_config(assistant=profile)
            rag_index_dir = get_rag_index_dir()
            rag_embedding_model = get_rag_embedding_model()
            mydata_dir = get_mydata_dir()
            coding_is_allowed_now = get_coding_is_allowed()
            training_config_path = get_training_config_path()

            handler = get_role_chat_handler(profile)
            if handler is not None:
                turn_ctx = RoleChatTurnContext(
                    page=page,
                    state=state,
                    graph_ref=graph_ref,
                    token=token,
                    turn_id=turn_id,
                    assistant_display=asst,
                    profile=profile,
                    provider=provider,
                    cfg=cfg,
                    rag_index_dir=rag_index_dir,
                    rag_embedding_model=rag_embedding_model,
                    mydata_dir=mydata_dir,
                    coding_is_allowed=coding_is_allowed_now,
                    training_config_path=training_config_path,
                    apply_from_assistant=apply_from_assistant,
                    set_graph=set_graph,
                    get_recent_changes=get_recent_changes,
                    on_show_run_console=on_show_run_console,
                    show_run_current_graph=_run_current_graph_effective(profile),
                    run_current_graph_cb=run_current_graph_cb,
                    last_apply_result_ref=last_apply_result_ref,
                    stream_buffer_ref=stream_buffer_ref,
                    is_current_run=_is_current_run,
                    toast=lambda m: _toast(page, m),
                    set_inline_status=_set_inline_status,
                    clear_stream_row=_clear_stream_row,
                    prepare_stream_row=_prepare_stream_row,
                    append_message=_append,
                    replace_assistant_message_row=_replace_assistant_message_row,
                    run_workflow_streaming=_run_workflow_with_streaming,
                    persist_history_debounced=_persist_history_debounced,
                    workflow_debug_log=_workflow_debug_log,
                    record_llm_prompt_view=(chat_panel_api or {}).get("record_llm_prompt_view"),
                )
                await handler.run_turn(turn_ctx, message_for_workflow=message_for_workflow)
            else:
                if not _is_current_run(token):
                    return
                _set_inline_status(None)
                _append(
                    "assistant",
                    f"Assistant role {profile!r} is listed in the chat dropdown but has no turn handler wired yet.",
                    meta={
                        "turn_id": turn_id,
                        "assistant": asst,
                        "source": "error",
                        "error_type": "unsupported_chat_role",
                    },
                )
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
            # LLM-specific wording is handled in LLMAgent (format_exception); this catches other failures in _run().
            if not _is_current_run(token):
                return
            _set_inline_status(None)
            _append(
                "assistant",
                str(ex).strip() or type(ex).__name__,
                meta={"turn_id": turn_id, "assistant": assistant_dd.value, "source": "error", "error_type": type(ex).__name__},
            )
        finally:
            if _is_current_run(token):
                _set_inline_status(None)
                _clear_stream_row()
                _set_busy(False)

    def _send_from_field(field: ft.TextField) -> None:
        text = (field.value or "").strip()
        ref_block = refs_controller.format_for_prompt()
        if state.busy or (not text and not ref_block):
            return
        cmd_lang = parse_session_language_command(text)
        if cmd_lang is not None:
            field.value = ""
            turn_id = _new_id()
            # Same double-submit guard as a normal send (no assistant run; re-enable below).
            state.busy = True
            input_tf_first.disabled = True
            input_tf.disabled = True
            safe_update(input_tf_first, input_tf)
            _append(
                "user",
                text,
                meta={"turn_id": turn_id, "assistant": assistant_dd.value, "source": "user_submit"},
            )
            state.session_language = cmd_lang
            ack = (
                "Session language cleared. The next Workflow Designer reply will pin a new language when the detector returns one."
                if cmd_lang == ""
                else f"Session language set to: {cmd_lang}"
            )
            _append(
                "assistant",
                ack,
                meta={
                    "turn_id": turn_id,
                    "assistant": assistant_dd.value,
                    "source": "session_language_command",
                },
            )
            _workflow_debug_log(f"session_language command -> {cmd_lang!r}")
            if not state.has_sent_any:
                _after_first_send()
            state.busy = False
            input_tf_first.disabled = False
            input_tf.disabled = False
            safe_update(input_tf_first, input_tf)
            safe_update(field)
            _persist_history_debounced()
            return

        display_text = text
        if ref_block:
            display_text = ref_block + ("\n\n" + text if text else "")
        # Avoid refs row.update() here — it would round-trip to the client before the user bubble.
        refs_controller.clear_quiet()

        # Capture message for workflow at send time so it is never lost (used as inject_user_message.data).
        message_for_workflow = normalize_user_message_for_workflow(display_text)
        field.value = ""
        turn_id = _new_id()
        # Lock composer immediately so a second Enter cannot queue another send before the async chain runs.
        state.busy = True
        input_tf_first.disabled = True
        input_tf.disabled = True
        run_turn_holder: list[Any] = [None]

        async def _after_user_submit_io() -> None:
            # First user message: chat path + delta + menu persist already ran above in _flush_append_io.
            # Schedule title rename only while has_sent_any is still False; _after_first_send sets it True.
            if not state.has_sent_any:
                _schedule_name_from_first_message(text or display_text[:120])
            run_token = _next_run_token()
            _after_first_send()
            _set_busy(True)
            safe_update(field)
            run_fn = run_turn_holder[0]
            if run_fn is not None:
                await run_fn(run_token)

        _append(
            "user",
            display_text,
            meta={"turn_id": turn_id, "assistant": assistant_dd.value, "source": "user_submit"},
            after_io=_after_user_submit_io,
            skip_messages_col_update=True,
        )
        # One client sync for user row + status + refs + inputs (avoids a full messages_col update
        # before status, which re-sent the entire history and delayed the status line on long chats).
        _set_inline_status("Planning next moves…", flush=False)
        safe_update(messages_col, refs_chips_row, input_tf_first, input_tf)
        safe_page_update(page)

        async def _bound_chat_turn(t: int) -> None:
            await _run_chat_turn(t, turn_id=turn_id, message_for_workflow=message_for_workflow)

        run_turn_holder[0] = _bound_chat_turn


    input_tf_first.on_submit = lambda _e: _send_from_field(input_tf_first)
    input_tf.on_submit = lambda _e: _send_from_field(input_tf)

    def _reset_chat_ui() -> None:
        # Reset state
        refs_controller.clear()
        state.history.clear()
        state.busy = False
        state.has_sent_any = False
        state.chat_path = None
        state.session_id = _new_id()
        state.created_at = _now_ts()
        state.session_language = ""

        # Reset inputs
        input_tf_first.value = ""
        input_tf.value = ""
        input_tf_first.disabled = False
        input_tf.disabled = False
        stop_btn_first.visible = False
        stop_btn_bottom.visible = False
        upload_btn_first.disabled = False
        upload_btn_bottom.disabled = False

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
            history_row_top_with_model,
            history_row_with_model,
            chat_title_top_txt,
            chat_title_txt,
            input_tf_first,
            input_tf,
            stop_btn_first,
            stop_btn_bottom,
            upload_btn_first,
            upload_btn_bottom,
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
        focus_handler.set_preference("first")

    # Populate recent chats on first render
    recent_menu.refresh()

    if chat_panel_api is not None:
        chat_panel_api["add_code_reference"] = refs_controller.add_code
        chat_panel_api["chat_graph_drag_group"] = CHAT_GRAPH_DRAG_GROUP

    inner_col = build_chat_inner_column(
        on_new_chat=_start_new_chat,
        assistant_dd=assistant_dd,
        chat_title_top_txt=chat_title_top_txt,
        refs_chips_row=refs_chips_row,
        top_input_container=top_input_container,
        history_row_top_with_model=history_row_top_with_model,
        messages_col=messages_col,
        bottom_input_row=bottom_input_row,
        history_row_with_model=history_row_with_model,
    )
    chat_drop_surface = ft.Container(content=inner_col, expand=True)

    def _chat_drop_will_accept(e: ft.DragWillAcceptEvent) -> None:
        chat_drop_surface.border = ft.border.all(1, ft.Colors.BLUE_400) if e.accept else None
        safe_update(chat_drop_surface)

    def _chat_drop_leave(_e: ft.DragTargetLeaveEvent) -> None:
        chat_drop_surface.border = None
        safe_update(chat_drop_surface)

    def _chat_drop_accept(e: ft.DragTargetEvent) -> None:
        chat_drop_surface.border = None
        safe_update(chat_drop_surface)
        try:
            data = getattr(getattr(e, "src", None), "data", None)
        except Exception:
            data = None
        if isinstance(data, dict) and data.get("kind") == "unit" and data.get("unit_id"):
            refs_controller.add_unit(str(data["unit_id"]))

    return ft.DragTarget(
        group=CHAT_GRAPH_DRAG_GROUP,
        content=chat_drop_surface,
        on_will_accept=_chat_drop_will_accept,
        on_leave=_chat_drop_leave,
        on_accept=_chat_drop_accept,
        expand=True,
    )

