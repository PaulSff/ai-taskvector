"""
Flet agents chat panel (messenger layer).

chat.py is a pure UI layer: it renders Flet rows, manages the
streaming bubble, and reacts to turn_driver outputs.
It delegates all session management, history, persistence, and workflow execution
to turn_driver.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, cast

import flet as ft
from flet import Border, BorderSide

from agents.roles import (
    ANALYST_ROLE_ID,
    RL_COACH_ROLE_ID,
    WORKFLOW_DESIGNER_ROLE_ID,
    get_role,
    list_chat_dropdown_role_ids,
)
from gui.chat.context.language_control import parse_session_language_command
from gui.chat.hooks import on_apply_hook
from gui.chat.session import (
    get_session,
    reset_session,
    stop_run,
    _history_dedupe_prefer_applied,
)
from gui.chat.session.chat_persistence import suggest_initial_chat_path
from gui.chat.session.history_store import load_chat_payload
from gui.chat.session.state import ChatSessionState
from gui.chat.turn_driver import (
    append_session_message,
    create_session,
    handle_turn,
    persist_session,
    restore_session,
)
from gui.chat.ui.chat_layout import ChatLayoutComponent
from gui.chat.ui.focus_handler import ChatFocusHandler
from gui.chat.ui.graph_references import GraphReferencesController
from gui.chat.ui.message_renderer import (
    build_agent_streaming_body,
    build_message_row,
    render_messages,
    streaming_agent_opened_code_fence,
)
from gui.chat.ui.recent_chats_menu import RecentChatsMenu
from gui.chat.ui.status_bar import StatusBarController
from gui.chat.utils import safe_page_update, safe_update
from gui.chat.utils.ids import _new_id
from gui.chat.utils.time import _now_ts
from gui.chat.utils.ui_utils import _toast
from gui.chat.utils.workflow_run_utils import _workflow_debug_log
from gui.components.rag_tab import run_rag_file_pick_copy_and_index
from gui.components.settings import (
    get_chat_history_dir,
    get_chat_stream_ui_interval_ms,
)
from gui.components.workflow_tab.process_graph import ProcessGraph
from gui.components.workflow_tab.workflows.core_workflows import (
    validate_graph_to_apply_for_canvas_inline,
)
from runtime.stream_ui_signals import INLINE_STATUS_PREFIX


CHAT_GRAPH_DRAG_GROUP = "chat_graph_ref"


agentDisplay = str  # role_name from dropdown (see list_chat_dropdown_role_ids)

CHAT_HISTORY_SCHEMA_VERSION = 3
CHAT_AUTOSAVE_DEBOUNCE_S = 0.45


def build_agents_chat_panel(
    page: ft.Page,
    *,
    graph_ref: list[ProcessGraph | None],
    set_graph: Callable[[ProcessGraph | None], None],
    apply_from_agent: Callable[[ProcessGraph | None], None] | None = None,
    get_recent_changes: Callable[[], Awaitable[str | None]] | None = None,
    on_undo: Callable[[], None] | None = None,
    on_redo: Callable[[], None] | None = None,
    show_run_current_graph: bool = False,
    on_show_run_console: Callable[[dict], None] | None = None,
    chat_panel_api: dict[str, Any] | None = None,
    on_turn_status=None,
) -> ft.Control:
    """
    Build the right-column agents chat panel.
    Applies Workflow Designer edits to the current graph.
    """
    _dropdown_role_ids = list_chat_dropdown_role_ids()
    if not _dropdown_role_ids:
        _dropdown_role_ids = (
            WORKFLOW_DESIGNER_ROLE_ID,
            ANALYST_ROLE_ID,
            RL_COACH_ROLE_ID,
        )
    _chat_agent_display_by_role = {
        rid: get_role(rid).role_name for rid in _dropdown_role_ids
    }
    _chat_role_by_display = {get_role(rid).role_name: rid for rid in _dropdown_role_ids}
    _chat_display_names = frozenset(_chat_role_by_display.keys())
    _default_chat_display = _chat_agent_display_by_role[_dropdown_role_ids[0]]

    agent_dd = ft.Dropdown(
        value=_default_chat_display,
        content_padding=2,
        width=166,
        height=26,
        color=ft.Colors.GREY_400,
        text_style=ft.TextStyle(size=11),
        border_color=ft.Colors.GREY_800,
        border_width=0,
        options=[
            ft.dropdown.Option(_chat_agent_display_by_role[rid])
            for rid in _dropdown_role_ids
        ],
    )

    def _agent_profile_key(v: str | None) -> str:
        label = (v or "").strip()
        return _chat_role_by_display.get(label, _dropdown_role_ids[0])

    state = ChatSessionState(
        history=[],
        busy=False,
        has_sent_any=False,
        session_id="",  # owned by turn_driver session
        created_at="",  # owned by turn_driver session
        chat_path=None,  # owned by turn_driver session
        session_language="",  # owned by turn_driver session
    )
    # Single turn_driver session — owns history, persistence, and workflow execution.
    _td_sid: str = create_session(None)
    _td_session_maybe = get_session(_td_sid)
    assert _td_session_maybe is not None, (
        "turn_driver session must exist after create_session"
    )
    _td_session = _td_session_maybe
    _workflow_debug_log("enabled=1 (chat panel initialized)")

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

    chat_component = ChatLayoutComponent(
        min_lines=4,
        max_lines=12,
        on_stop_click=lambda _e: _on_stop(),
        on_upload_click=lambda _e: (
            page.run_task(run_rag_file_pick_copy_and_index, page),
            None,
        )[1],
    )

    first_composer = chat_component.composer_parts

    bottom_component = ChatLayoutComponent(
        min_lines=2,
        max_lines=6,
        on_stop_click=lambda _e: _on_stop(),
        on_upload_click=lambda _e: (
            page.run_task(run_rag_file_pick_copy_and_index, page),
            None,
        )[1],
    )

    bottom_composer = bottom_component.composer_parts

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
    # stream_ui_min_interval_s is set inside turn_driver; not needed directly in chat.py
    get_chat_stream_ui_interval_ms()  # ensure setting is loaded

    # controls = build_workflow_run_console(page, graph_ref, _toast)

    # Chat title.
    # Before first message: show above the first-message composer.
    # After first message: show at top of messages scroll area.
    chat_title_top_txt = ft.Text(
        "new_chat", size=12, color=ft.Colors.GREY_500, visible=True
    )
    chat_title_txt = ft.Text(
        "new chat", size=12, color=ft.Colors.GREY_500, visible=False
    )

    messages_col = ft.Column(
        [chat_title_txt],
        scroll=ft.ScrollMode.AUTO,
        auto_scroll=False,  # required for scroll_to(); we scroll during streaming explicitly
        expand=True,
        spacing=8,
    )

    async def _scroll_chat_to_bottom() -> None:
        """Keep the message list pinned to the bottom while the agent streams tokens."""
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

    # Debounced full-snapshot autosave (delegates to turn_driver.persist_session).
    _persist_token_ref: list[int] = [0]

    def _persist_session_debounced(delay_s: float = CHAT_AUTOSAVE_DEBOUNCE_S) -> None:
        _persist_token_ref[0] += 1
        my_token = _persist_token_ref[0]

        async def _run() -> None:
            try:
                await asyncio.sleep(max(0.0, delay_s))
            except Exception:
                return
            if my_token != _persist_token_ref[0]:
                return
            persist_session(_td_sid, agent_selected=agent_dd.value)

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
            persist=_persist_session_debounced,
            toast=_toast_now,
            on_undo=on_undo,
            on_redo=on_redo,
            bubble_width=None,
        )

    def _render_messages_from_history() -> None:
        messages_col.controls = [chat_title_txt] if state.has_sent_any else [chat_title_top_txt]

        render_messages(
            messages_col=messages_col,
            chat_title_txt=chat_title_txt,
            history=_history_dedupe_prefer_applied(_td_session.history), # prevent duplicate history rendering after loading from dropdown
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
        msg: Optional[dict[str, Any]] = None,
        meta: dict[str, Any] | None = None,
        after_io: Callable[[], Coroutine[Any, Any, None]] | None = None,
        skip_messages_col_update: bool = False,
    ) -> dict[str, Any]:
        """
        Insert a message row in the Flet UI. Purely visual — no history tracking, no I/O.
        Session history and persistence are owned by turn_driver (handle_turn /
        append_session_message). Pass a pre-built ``msg`` dict to reuse the exact object
        that was already stored in the session; if omitted a transient dict is created for
        local-only messages (e.g. session-language command acknowledgements).
        """
        if msg is None:
            msg = {"id": _new_id(), "ts": _now_ts(), "role": role, "content": content}
            if meta:
                msg.update(meta)
        row = _row_builder(msg)
        msg["_flet_row"] = row
        # Smooth inline for agent turns: replace the live stream row in-place with the
        # final rendered row so there is never a duplicate-row flash or layout jump.
        stream_row = stream_row_ref[0]
        if (
            role == "agent"
            and stream_row is not None
            and stream_row in messages_col.controls
        ):
            idx = messages_col.controls.index(stream_row)
            messages_col.controls[idx] = row  # atomic replace — no insert+remove gap
            # Hand off: stream row is gone; _clear_stream_row in finally will be a no-op
            stream_row_ref[0] = None
            stream_wrapper_ref[0] = None
            stream_bubble_ref[0] = None
            stream_plain_txt_ref[0] = None
            stream_buffer_ref[0] = ""
            stream_rich_ref[0] = False
        elif stream_row is not None and stream_row in messages_col.controls:
            idx = messages_col.controls.index(stream_row)
            messages_col.controls.insert(idx, row)
        else:
            messages_col.controls.append(row)
        if not skip_messages_col_update:
            safe_update(messages_col)

        async def _flush_append_io() -> None:
            await asyncio.sleep(0)
            # Ensure a chat file exists before handle_turn runs (in after_io) so that
            # delta writes land in the right place and the recent-menu can show the new
            # chat immediately without waiting for the workflow to complete.
            was_new_chat = _td_session.chat_path is None
            if was_new_chat:
                tmp = suggest_initial_chat_path(chat_history_dir)
                _td_session.chat_path = tmp
                _set_chat_title_from_path(tmp)
            await _scroll_chat_to_bottom()
            if was_new_chat and _td_session.chat_path is not None:

                async def _menu_refresh_and_snapshot() -> None:
                    await asyncio.sleep(0)
                    if _td_session.chat_path is None:
                        return
                    _recent_menu_refresh_and_select(_td_session.chat_path.name)
                    _persist_session_debounced()

                page.run_task(_menu_refresh_and_snapshot)

            if after_io is not None:
                await after_io()

        page.run_task(_flush_append_io)
        return msg


    # In-progress agent response row (UI-only; used for streaming).
    stream_row_ref: list[ft.Row | None] = [None]
    stream_bubble_ref: list[ft.Container | None] = [None]
    stream_plain_txt_ref: list[ft.Text | None] = [None]
    stream_buffer_ref: list[str] = [""]
    stream_rich_ref: list[bool] = [False]
    stream_wrapper_ref: list[Optional[ft.Column]] = [None]

    def _clear_stream_row() -> None:
        row = stream_row_ref[0]
        if row is not None and row in messages_col.controls:
            messages_col.controls.remove(row)
            safe_update(messages_col)
            safe_page_update(page)
        if row is not None:
            stream_row_ref[0] = None
            stream_bubble_ref[0] = None
            stream_plain_txt_ref[0] = None
            stream_wrapper_ref[0] = None
            stream_buffer_ref[0] = ""
            stream_rich_ref[0] = False

    def _ensure_stream_row() -> None:
        if stream_row_ref[0] is not None:
            return

        txt = ft.Text(
            "", size=12, color=ft.Colors.GREY_200, selectable=True, no_wrap=False
        )
        stream_plain_txt_ref[0] = txt

        # persistent wrapper that will keep the same control instance
        wrapper = ft.Column(controls=[txt], spacing=0)
        stream_wrapper_ref[0] = wrapper

        bubble = ft.Container(
            content=wrapper,  # use wrapper instead of txt
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border_radius=8,
            bgcolor=ft.Colors.TRANSPARENT,
            expand=True,
        )
        stream_bubble_ref[0] = bubble

        # Align like agent bubbles (left, with slight indent)
        row = ft.Row(
            [
                ft.Container(
                    expand=True, content=bubble, padding=ft.Padding.only(left=12)
                )
            ]
        )
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
        w = stream_wrapper_ref[0]
        if b is not None and t is not None and w is not None:
            t.value = ""
            w.controls[:] = [
                t
            ]  # reset to plain-text; rich mode replaces wrapper.controls
            b.content = (
                w  # wrapper is always the bubble's direct content — never swap it out
            )
            safe_update(b)
        safe_page_update(page)
        page.run_task(_scroll_chat_to_bottom)

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
        _next_run_token()  # prevent stale stream callbacks from updating the UI
        stop_run(_td_sid)  # signal turn_driver's streaming consumer to stop
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

        payload = load_chat_payload(path)
        if payload is None:

            async def _toast_load_fail() -> None:
                await _toast(page, "Could not load chat file")

            page.run_task(_toast_load_fail)
            return

        # Restore session state into turn_driver (history, language, path, etc.)
        restore_session(_td_sid, path=path, payload=payload)

        _set_chat_title_from_path(path)
        state.has_sent_any = _td_session.has_sent_any
        _workflow_debug_log(f"loaded session_language={_td_session.session_language!r}")

        asst_sel = payload.get("agent_selected")
        if asst_sel in _chat_display_names:
            agent_dd.value = asst_sel
            try:
                agent_dd.update()
            except Exception:
                pass
            _update_model_label()

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

    recent_menu = RecentChatsMenu(
        page=page, chat_history_dir=chat_history_dir, on_select=_load_chat_file
    ).build()
    recent_menu_ref[0] = recent_menu
    recent_menu.refresh()

    history_row_top = cast(ft.Row, recent_menu.row_top)
    history_row_bottom = cast(ft.Row, recent_menu.row_bottom)

    # Model name from settings (shown to the right of the chat history dropdown in both first-message and bottom layout)
    model_label = ft.Text("", size=11, color=ft.Colors.GREY_400)
    model_label_top = ft.Text("", size=11, color=ft.Colors.GREY_400)

    def _update_model_label() -> None:
        profile = _agent_profile_key(agent_dd.value)
        value = get_role(profile).ollama_model or "—"
        model_label.value = value
        model_label_top.value = value
        safe_update(model_label, model_label_top)
        safe_page_update(page)

    _update_model_label()
    wrapper_row_ref: list[ft.Row | None] = [None]
    top_wrapper_row_ref: list[ft.Row | None] = [None]
    history_row_top_with_model = chat_component.build_history_row_with_model(
        history_row_top, model_label_top, visible=history_row_top.visible
    )
    top_wrapper_row_ref[0] = history_row_top_with_model
    history_row_with_model = chat_component.build_history_row_with_model(
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
        )

    # Toggle input placement: top (first message) -> bottom (subsequent)
    top_input_container = ft.Container(content=stacked_first, visible=True)
    bottom_input_row_controls: list[ft.Control] = [stacked_bottom]
    bottom_input_row = ft.Row(bottom_input_row_controls, spacing=8, visible=False)

    def _on_agent_dd_change(_e: ft.ControlEvent | None) -> None:
        _update_model_label()

    setattr(agent_dd, "on_change", _on_agent_dd_change)

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
        safe_update(
            top_input_container,
            bottom_input_row,
            history_row_top_with_model,
            history_row_with_model,
            chat_title_top_txt,
            chat_title_txt,
        )
        safe_page_update(page)

    # Hoisted out of _send_from_field so Enter does not synchronously re-parse a large nested def
    # before the handler returns (that delay blocked the status line from painting).
    async def _run_chat_turn(
        token: int, *, turn_id: str, user_msg: dict[str, Any], message_for_workflow: str
    ) -> None:
        """Run one agent turn via turn_driver.handle_turn()."""
        try:
            if not _is_current_run(token):
                return

            profile = _agent_profile_key(agent_dd.value or _default_chat_display)

            _graph = graph_ref[0]
            if _graph is None:
                graph_dict = None
            elif hasattr(_graph, "model_dump"):
                graph_dict = _graph.model_dump(by_alias=True)
            elif isinstance(_graph, dict):
                graph_dict = _graph
            else:
                graph_dict = None

            _prepare_stream_row()

            # Streaming callback: turn_driver calls this with the accumulated buffer
            # (or an INLINE_STATUS_PREFIX piece) on each UI refresh tick.
            async def _stream_cb(session_id: str, chunk: str) -> None:
                if chunk.startswith(INLINE_STATUS_PREFIX):
                    rest = chunk[len(INLINE_STATUS_PREFIX) :]
                    _set_inline_status(rest if rest else None)
                    safe_page_update(page)
                    return
                _ensure_stream_row()
                wrapper = stream_wrapper_ref[0]
                if wrapper is None:
                    return
                if not stream_rich_ref[0] and streaming_agent_opened_code_fence(chunk):
                    stream_rich_ref[0] = True
                if stream_rich_ref[0]:
                    wrapper.controls[:] = [
                        build_agent_streaming_body(
                            page=page,
                            toast=_toast_now,
                            on_undo=on_undo,
                            on_redo=on_redo,
                            content=chunk,
                            bubble_width=None,
                        )
                    ]
                    wrapper.update()
                else:
                    t = stream_plain_txt_ref[0]
                    if t is None:
                        return
                    t.value = chunk
                    t.update()
                safe_page_update(page)
                await _scroll_chat_to_bottom()
                _set_inline_status(None)

            # initialize once per render/update loop scope
            apply_state = {
                "last_graph_to_apply": None,
                "graph_apply_error": None,
                "graph_applied": False,
                "is_initial_apply_done": False,
            }

            async def _on_apply(inner_msg: dict[str, Any]) -> None:
                await on_apply_hook(
                    token=token,
                    inner_msg=inner_msg,
                    page=page,
                    is_current_run=_is_current_run,
                    toast=_toast,
                    validate_graph_inline=validate_graph_to_apply_for_canvas_inline,
                    safe_page_update=safe_page_update,
                    scroll_chat_to_bottom=_scroll_chat_to_bottom,  # passthrough; not used
                    apply_fn_from_agent=apply_from_agent,
                    set_graph=set_graph,
                    state=apply_state,
                )

            # After turn_driver renames the file, sync UI title and recent-menu.
            def _on_rename(new_path: Path) -> None:
                _set_chat_title_from_path(new_path)
                _recent_menu_refresh_and_select(new_path.name)

            outputs = await handle_turn(
                _td_sid,
                message_for_workflow,
                "taskvector",
                graph_dict=graph_dict,
                role_id=profile,
                recent_changes=(
                    await get_recent_changes()
                    if get_recent_changes is not None
                    else None
                ),
                pre_built_user_msg=user_msg,
                on_rename=_on_rename,
                stream_callback=_stream_cb,
                on_apply=_on_apply,
                on_turn_status=on_turn_status,
            )

            if not _is_current_run(token):
                return

            # handle_turn returns the orchestrator unit's output dict directly.
            orch_out: dict[str, Any] = outputs or {}

            # ── role output → update dropdown to show which role actually responded ──
            role_out = orch_out.get("role")
            if isinstance(role_out, dict) and role_out.get("role_id"):
                new_role_id = role_out["role_id"]
                if new_role_id in _dropdown_role_ids:
                    target_display = _chat_agent_display_by_role.get(new_role_id)
                    if target_display and agent_dd.value != target_display:
                        agent_dd.value = target_display
                        try:
                            agent_dd.update()
                        except Exception:
                            pass
                        _update_model_label()

            agent_msg = _td_session.history[-1] if _td_session.history else None

            if agent_msg and agent_msg.get("role") == "agent":
                # Always replace streaming row with the rendered agent row
                _append("agent", agent_msg.get("content") or "", msg=agent_msg)
                _persist_session_debounced()

        except Exception as ex:
            if not _is_current_run(token):
                return
            _set_inline_status(None)
            err_content = str(ex).strip() or type(ex).__name__
            err_msg: dict[str, Any] = {
                "id": _new_id(),
                "ts": _now_ts(),
                "role": "agent",
                "content": err_content,
                "turn_id": turn_id,
                "agent": agent_dd.value,
                "source": "error",
                "error_type": type(ex).__name__,
            }
            append_session_message(_td_sid, err_msg)
            _append("agent", err_content, msg=err_msg)
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
            input_tf_first.value = ""
            input_tf.value = ""
            turn_id = _new_id()
            # Same double-submit guard as a normal send (no agent run; re-enable below).
            state.busy = True
            input_tf_first.disabled = True
            input_tf.disabled = True
            safe_update(input_tf_first, input_tf)
            user_msg_lc: dict[str, Any] = {
                "id": _new_id(),
                "ts": _now_ts(),
                "role": "user",
                "content": text,
                "turn_id": turn_id,
                "agent": agent_dd.value,
                "source": "user_submit",
            }
            _td_session.session_language = cmd_lang
            ack = (
                "Session language cleared. The next Workflow Designer reply will pin a new language when the detector returns one."
                if cmd_lang == ""
                else f"Session language set to: {cmd_lang}"
            )
            ack_msg: dict[str, Any] = {
                "id": _new_id(),
                "ts": _now_ts(),
                "role": "agent",
                "content": ack,
                "turn_id": turn_id,
                "agent": agent_dd.value,
                "source": "session_language_command",
            }
            append_session_message(_td_sid, user_msg_lc)
            append_session_message(_td_sid, ack_msg)
            _append("user", text, msg=user_msg_lc)
            _append("agent", ack, msg=ack_msg)
            _workflow_debug_log(f"session_language command -> {cmd_lang!r}")
            if not state.has_sent_any:
                _after_first_send()
            state.busy = False
            input_tf_first.disabled = False
            input_tf.disabled = False
            safe_update(input_tf_first, input_tf)
            _persist_session_debounced()
            return

        display_text = text
        if ref_block:
            display_text = ref_block + ("\n\n" + text if text else "")
        # Avoid refs row.update() here — it would round-trip to the client before the user bubble.
        refs_controller.clear_quiet()

        # Capture message for workflow at send time so it is never lost.
        message_for_workflow = display_text
        # Both composers exist (top vs bottom after first message); always clear both.
        input_tf_first.value = ""
        input_tf.value = ""
        turn_id = _new_id()
        # Lock composer immediately so a second Enter cannot queue another send before the async chain runs.
        state.busy = True
        input_tf_first.disabled = True
        input_tf.disabled = True
        run_turn_holder: list[Any] = [None]

        # Pre-build user message dict so the same object is stored in both the
        # Flet row and the turn_driver session history (via pre_built_user_msg).
        user_msg: dict[str, Any] = {
            "id": _new_id(),
            "ts": _now_ts(),
            "role": "user",
            "content": display_text,
            "turn_id": turn_id,
            "agent": agent_dd.value,
            "source": "user_submit",
        }

        async def _after_user_submit_io() -> None:
            # Filename suggestion is handled by turn_driver on the first handle_turn call.
            run_token = _next_run_token()
            _after_first_send()
            _set_busy(True)
            safe_update(input_tf_first, input_tf)
            run_fn = run_turn_holder[0]
            if run_fn is not None:
                await run_fn(run_token)

        _append(
            "user",
            display_text,
            msg=user_msg,
            after_io=_after_user_submit_io,
            skip_messages_col_update=True,
        )
        # One client sync for user row + status + refs + inputs (avoids a full messages_col update
        # before status, which re-sent the entire history and delayed the status line on long chats).
        _set_inline_status("Planning next steps…", flush=False)
        safe_update(messages_col, refs_chips_row, input_tf_first, input_tf)
        safe_page_update(page)

        async def _bound_chat_turn(t: int) -> None:
            await _run_chat_turn(
                t,
                turn_id=turn_id,
                user_msg=user_msg,
                message_for_workflow=message_for_workflow,
            )

        run_turn_holder[0] = _bound_chat_turn

    input_tf_first.on_submit = lambda _e: _send_from_field(input_tf_first)
    input_tf.on_submit = lambda _e: _send_from_field(input_tf)

    def _reset_chat_ui() -> None:
        # Reset UI state and clear the turn_driver session (history, path, language, etc.)
        refs_controller.clear()
        reset_session(_td_sid)
        state.busy = False
        state.has_sent_any = False

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

    def _start_new_chat(_e: object) -> None:
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
        chat_panel_api["add_file_path_reference"] = refs_controller.add_file_path
        chat_panel_api["chat_graph_drag_group"] = CHAT_GRAPH_DRAG_GROUP
        chat_panel_api["refresh_model_label"] = _update_model_label

    inner_col = chat_component.build_chat_inner_column(
        on_new_chat=_start_new_chat,
        agent_dd=agent_dd,
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
        chat_drop_surface.border = (
            Border(
                left=BorderSide(1, ft.Colors.BLUE_400),
                top=BorderSide(1, ft.Colors.BLUE_400),
                right=BorderSide(1, ft.Colors.BLUE_400),
                bottom=BorderSide(1, ft.Colors.BLUE_400),
            )
            if e.accept
            else None
        )
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
        if (
            isinstance(data, dict)
            and data.get("kind") == "unit"
            and data.get("unit_id")
        ):
            refs_controller.add_unit(str(data["unit_id"]))

    return ft.DragTarget(
        group=CHAT_GRAPH_DRAG_GROUP,
        content=chat_drop_surface,
        on_will_accept=_chat_drop_will_accept,
        on_leave=_chat_drop_leave,
        on_accept=_chat_drop_accept,
        expand=True,
    )
