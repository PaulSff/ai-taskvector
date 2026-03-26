"""
Flet assistants chat panel: Workflow Designer / RL Coach in the right column.

Chat always runs a workflow per assistant (no direct LLM path). Only the workflow file and handler differ.
- Workflow Designer: assistant_workflow.json; first message also runs create_filename.json for chat title.
- RL Coach: rl_coach_workflow.json.
"""
from __future__ import annotations

import asyncio
import os
import queue
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from typing import Any, Callable, Literal

import flet as ft

from gui.flet.components.workflow.core_workflows import validate_graph_to_apply_for_canvas
from gui.flet.chat_with_the_assistants.chat_turn_context import (
    format_previous_turn,
    normalize_user_message_for_workflow,
)
from gui.flet.chat_with_the_assistants.rl_coach_handler import (
    build_rl_coach_initial_inputs,
    build_rl_coach_unit_param_overrides,
    get_training_config_dict,
    get_training_config_summary,
    get_training_results_follow_up,
    run_rl_coach_workflow,
)
from gui.flet.chat_with_the_assistants.todo_list_manager import get_summary_params
from gui.flet.chat_with_the_assistants.create_filename import run_create_filename_workflow
from gui.flet.chat_with_the_assistants.workflow_designer_handler import (
    build_assistant_workflow_initial_inputs,
    build_assistant_workflow_unit_param_overrides,
    build_self_correction_retry_inputs,
    get_runtime_for_prompts,
    refresh_last_apply_result_after_canvas_apply,
    run_assistant_workflow,
    run_current_graph,
)
from gui.flet.chat_with_the_assistants.workflow_designer_followups import (
    ParserFollowUpContext,
    PostApplyFlags,
    PostApplyFollowUpContext,
    run_parser_output_follow_up_chain,
    run_post_apply_follow_up_rounds,
)
from runtime.run import WorkflowTimeoutError
from gui.flet.components.workflow.process_graph import ProcessGraph

from gui.flet.components.settings import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    get_coding_is_allowed,
    get_chat_history_dir,
    get_llm_provider,
    get_llm_provider_config,
    get_mydata_dir,
    get_workflow_designer_max_follow_ups,
    get_rag_embedding_model,
    get_rag_index_dir,
)
from gui.flet.tools.notifications import show_toast

from gui.flet.chat_with_the_assistants.chat_persistence import (
    build_chat_payload,
    suggest_initial_chat_path,
)
from gui.flet.chat_with_the_assistants.history_store import (
    load_chat_payload,
    slugify_filename,
    unique_path,
    write_chat_payload,
)
from gui.flet.chat_with_the_assistants.language_control import (
    default_wf_language_hint,
    finalize_workflow_designer_turn_session_language,
    maybe_pin_session_language_from_workflow_response,
    parse_session_language_command,
)
from gui.flet.chat_with_the_assistants.load_chat_history import load_chat_session
from gui.flet.chat_with_the_assistants.message_renderer import (
    build_assistant_streaming_body,
    build_message_row,
    render_messages,
    streaming_assistant_opened_code_fence,
)
from gui.flet.chat_with_the_assistants.rag_context import _UNITS_DIR
from gui.flet.chat_with_the_assistants.recent_chats_menu import RecentChatsMenu
from gui.flet.chat_with_the_assistants.status_bar import StatusBarController
from gui.flet.chat_with_the_assistants.state import ChatSessionState
from gui.flet.chat_with_the_assistants.ui_utils import safe_page_update, safe_update
from gui.flet.chat_with_the_assistants.graph_references import GraphReferencesController
from gui.flet.chat_with_the_assistants.chat_layout import (
    build_chat_composer,
    build_chat_inner_column,
    build_history_row_with_model,
)
from gui.flet.chat_with_the_assistants.focus_handler import ChatFocusHandler
from gui.flet.components.rag_tab import run_rag_file_pick_copy_and_index

CHAT_GRAPH_DRAG_GROUP = "chat_graph_ref"


AssistantType = Literal["Workflow Designer", "RL Coach"]

CHAT_HISTORY_SCHEMA_VERSION = 3


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

    def _ensure_chat_file() -> None:
        """Create a temporary chat file name on first write."""
        if state.chat_path is not None:
            return
        tmp = suggest_initial_chat_path(chat_history_dir)
        state.chat_path = tmp
        _set_chat_title_from_path(tmp)
        _recent_menu_refresh_and_select(tmp.name)
        _persist_history()

    def _schedule_name_from_first_message(first_message: str) -> None:
        """
        Run create_filename workflow to suggest a short filename base (snake_case), then rename the chat file.
        Falls back to slugifying the first message if the workflow fails.
        """
        _ensure_chat_file()

        async def _run() -> None:
            base = ""
            try:
                profile = _assistant_profile_key(assistant_dd.value)
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
        page.run_task(_scroll_chat_to_bottom)

    def _append(role: str, content: str, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        _ensure_chat_file()
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
        try:
            messages_col.update()
            page.update()
        except Exception:
            pass
        page.run_task(_scroll_chat_to_bottom)
        _persist_history()
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
            _persist_history()
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

    async def _run_workflow_with_streaming(run_fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run a workflow in a thread while an async consumer on the main thread updates the stream row from a queue. This way streamed tokens are visible during generation (page.run_task from the executor thread does not run until the main thread finishes awaiting the thread)."""
        stream_queue: queue.Queue[str | None] = queue.Queue()
        stream_cb = stream_queue.put

        def run_in_thread() -> Any:
            result = run_fn(*args, **kwargs, stream_callback=stream_cb)
            stream_queue.put(None)  # sentinel so consumer exits
            return result

        async def stream_consumer() -> None:
            while True:
                piece = await asyncio.get_event_loop().run_in_executor(None, stream_queue.get)
                if piece is None:
                    break
                _ensure_stream_row()
                stream_buffer_ref[0] += piece
                text = stream_buffer_ref[0]
                b = stream_bubble_ref[0]
                t = stream_plain_txt_ref[0]
                if b is None or t is None:
                    continue
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
        on_stop=_on_stop,
        safe_update=safe_update,
        safe_page_update=safe_page_update,
    )

    def _set_inline_status(msg: str | None) -> None:
        status_bar.set_status(msg)

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
        if asst_sel in ("Workflow Designer", "RL Coach"):
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

    assistant_dd.on_change = lambda _: _update_model_label()

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
            run_current_graph_cb.update()
        input_tf_first.update()
        input_tf.update()
        try:
            stop_btn_first.update()
            stop_btn_bottom.update()
            upload_btn_first.update()
            upload_btn_bottom.update()
        except Exception:
            pass
        if not v:
            _set_inline_status(None)
            _clear_stream_row()
        status_bar.set_stop_visible(False)
        page.update()

    # Toggle input placement: top (first message) -> bottom (subsequent)
    top_input_container = ft.Container(content=stacked_first, visible=True)
    run_current_graph_cb = ft.Checkbox(label="Run current graph", value=False, tooltip="(-dev) Execute the current workflow with this message instead of assistant_workflow.json")
    bottom_input_row_controls: list[ft.Control] = [stacked_bottom]
    if show_run_current_graph:
        bottom_input_row_controls.append(run_current_graph_cb)
    bottom_input_row = ft.Row(bottom_input_row_controls, spacing=8, visible=False)

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

    def _send_from_field(field: ft.TextField) -> None:
        text = (field.value or "").strip()
        ref_block = refs_controller.format_for_prompt()
        if state.busy or (not text and not ref_block):
            return
        cmd_lang = parse_session_language_command(text)
        if cmd_lang is not None:
            field.value = ""
            field.update()
            turn_id = _new_id()
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
            _persist_history()
            return

        display_text = text
        if ref_block:
            display_text = ref_block + ("\n\n" + text if text else "")
        refs_controller.clear()

        # Capture message for workflow at send time so it is never lost (used as inject_user_message.data).
        message_for_workflow = normalize_user_message_for_workflow(display_text)
        field.value = ""
        field.update()
        turn_id = _new_id()
        # On first message only: two parallel requests. (1) Title: direct LLM call (bypasses workflow).
        # (2) Chat response: same message goes through assistant_workflow.json in _run() below.
        if not state.has_sent_any:
            _schedule_name_from_first_message(text or display_text[:120])
        _append(
            "user",
            display_text,
            meta={"turn_id": turn_id, "assistant": assistant_dd.value, "source": "user_submit"},
        )
        token = _next_run_token()
        _set_inline_status("Planning next moves…")
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

                if asst == "Workflow Designer":
                    # Workflow-driven: run assistant_workflow.json, consume merge_response.data. Phase 2: follow-up loop (file/RAG/web/browse/code_block) with statuses.
                    overrides = build_assistant_workflow_unit_param_overrides(
                        provider,
                        cfg,
                        str(get_rag_index_dir()),
                        get_rag_embedding_model(),
                        report_output_dir=str(Path(get_mydata_dir()) / "reports"),
                    )
                    _graph = graph_ref[0]
                    _graph_dict = _graph.model_dump(by_alias=True) if hasattr(_graph, "model_dump") else (_graph if isinstance(_graph, dict) else None)
                    overrides["graph_summary"] = get_summary_params(get_coding_is_allowed(), _graph_dict)
                    _set_inline_status("Planning next moves…")
                    follow_up_contexts_this_turn: list[str] = []
                    wf_lang_cell = [default_wf_language_hint(state.session_language)]
                    max_wd_follow_ups = get_workflow_designer_max_follow_ups()

                    async def _parser_output_follow_up_chain(resp: dict[str, Any]) -> dict[str, Any] | None:
                        ctx = ParserFollowUpContext(
                            page=page,
                            graph_ref=graph_ref,
                            state=state,
                            token=token,
                            turn_id=turn_id,
                            assistant_label=asst,
                            follow_up_contexts=follow_up_contexts_this_turn,
                            max_rounds=max_wd_follow_ups,
                            wf_language_hint=wf_lang_cell,
                            is_current_run=_is_current_run,
                            toast=lambda m: _toast(page, m),
                            set_inline_status=_set_inline_status,
                            append_message=_append,
                            prepare_stream_row=_prepare_stream_row,
                            normalize_user_message_for_workflow=normalize_user_message_for_workflow,
                            last_apply_result_ref=last_apply_result_ref,
                            get_recent_changes=get_recent_changes,
                            overrides=overrides,
                            run_workflow_streaming=_run_workflow_with_streaming,
                            get_runtime_for_prompts=get_runtime_for_prompts,
                            format_previous_turn=format_previous_turn,
                            on_show_run_console=on_show_run_console,
                        )
                        return await run_parser_output_follow_up_chain(ctx, resp)

                        return response

                    try:
                        # Show streaming bubble immediately so user sees tokens as they generate.
                        _prepare_stream_row()
                        # Use last user message from history as source of truth so the model always gets what was actually sent (avoids closure/async losing the message).
                        last_user_content = None
                        for m in reversed(state.history or []):
                            if isinstance(m, dict) and (m.get("role") or "").strip().lower() == "user":
                                last_user_content = (m.get("content") or m.get("content_for_display") or "")
                                break
                        user_message_for_workflow = normalize_user_message_for_workflow(
                            last_user_content if (last_user_content is not None and str(last_user_content).strip()) else message_for_workflow
                        )
                        # Language for injects: use pinned session_language or default until the first
                        # workflow response supplies merge_response.language (see maybe_pin_session_language_from_workflow_response).
                        _runtime = get_runtime_for_prompts(_graph)
                        initial_inputs = build_assistant_workflow_initial_inputs(
                            user_message_for_workflow,
                            _graph,
                            last_apply_result_ref[0],
                            get_recent_changes() if get_recent_changes else None,
                            runtime=_runtime,
                            coding_is_allowed=get_coding_is_allowed(),
                            previous_turn=format_previous_turn(state.history[:-1]),
                            language_hint=wf_lang_cell[0],
                            session_language=state.session_language,
                        )
                        # Run workflow with queue-based streaming so tokens appear during generation (main thread consumes queue while thread runs workflow).
                        use_current_graph = show_run_current_graph and run_current_graph_cb.value and graph_ref[0] is not None
                        if use_current_graph:
                            response = await _run_workflow_with_streaming(
                                run_current_graph,
                                graph_ref[0],
                                initial_inputs,
                                overrides,
                            )
                        else:
                            response = await _run_workflow_with_streaming(
                                run_assistant_workflow,
                                initial_inputs,
                                overrides,
                                None,  # execution_timeout_s default
                            )
                    except WorkflowTimeoutError as ex:
                        _set_inline_status(None)
                        content = f"(Request timed out after {getattr(ex, 'timeout_s', 300):.0f}s. Try again or check that the LLM/service is responding.)"
                        result = {"kind": "parse_error", "content_for_display": content, "apply_result": {}, "edits": []}
                        last_apply_result_ref[0] = None
                    except Exception as ex:
                        _set_inline_status(None)
                        content = f"(Workflow error: {ex})"
                        result = {"kind": "parse_error", "content_for_display": content, "apply_result": {}, "edits": []}
                        last_apply_result_ref[0] = None
                    else:
                        chained = await _parser_output_follow_up_chain(response)
                        if chained is None:
                            return
                        response = chained

                        # If report unit wrote a file, show status and trigger rag_update to index it.
                        report_out = response.get("report_output")
                        if (
                            _is_current_run(token)
                            and isinstance(report_out, dict)
                            and report_out.get("ok")
                        ):
                            _set_inline_status("Making report…")
                            try:
                                from gui.flet.components.settings import get_rag_update_workflow_path
                                from runtime.run import run_workflow
                                path = get_rag_update_workflow_path()
                                if path.exists():
                                    overrides_rag = {
                                        "rag_update": {
                                            "rag_index_data_dir": str(get_rag_index_dir()),
                                            "units_dir": str(_UNITS_DIR),
                                            "mydata_dir": str(get_mydata_dir()),
                                            "embedding_model": get_rag_embedding_model(),
                                        },
                                    }
                                    await asyncio.to_thread(
                                        run_workflow,
                                        path,
                                        initial_inputs={},
                                        unit_param_overrides=overrides_rag,
                                        format="dict",
                                    )
                            except Exception:
                                pass
                            if _is_current_run(token):
                                _set_inline_status(None)

                        raw_reply = response.get("reply")
                        if isinstance(raw_reply, dict) and "action" in raw_reply:
                            raw_reply = raw_reply.get("action") or ""
                        content = (raw_reply if isinstance(raw_reply, str) else str(raw_reply or "")).strip() or "(No response from model.)"
                        # If reply is empty but parser produced edits (e.g. no_edit), show a fallback so chat doesn't look broken
                        if content == "(No response from model.)":
                            po = response.get("parser_output")
                            edits = po if isinstance(po, list) else (po.get("edits") if isinstance(po, dict) else None)
                            if isinstance(edits, list) and edits:
                                content = "No graph changes requested."
                        wf_result = response.get("result") or {}
                        result = dict(wf_result)
                        result["apply_result"] = response.get("status") or wf_result.get("last_apply_result") or {}
                        ar0 = result.get("apply_result") or {}
                        if (
                            result.get("kind") != "apply_failed"
                            and isinstance(ar0, dict)
                            and ar0.get("attempted") is True
                            and ar0.get("success") is False
                        ):
                            result["kind"] = "apply_failed"
                        workflow_errors = response.get("workflow_errors") or []
                        # Only treat as "message didn't reach model" when LLMAgent reported it or error text clearly says so.
                        # (Aggregate can emit "required... user_message" even when the message did reach the model, e.g. keys param in_0 vs user_message.)
                        user_message_missing = any(
                            err
                            and (
                                (str(err[0]) == "llm_agent" and (err[1] or "").strip())
                                or "placeholder" in (err[1] or "").lower()
                                or "no message" in (err[1] or "").lower()
                            )
                            for err in workflow_errors
                        )
                        if user_message_missing:
                            content = "Your message didn't reach the model. Please try sending again."
                            result["content_for_display"] = content
                        else:
                            result["content_for_display"] = content
                        last_apply_result_ref[0] = wf_result.get("last_apply_result")
                        if workflow_errors and _is_current_run(token):
                            err_msg = workflow_errors[0][1][:150] if workflow_errors else ""
                            if len(workflow_errors) > 1:
                                err_msg += f" (+{len(workflow_errors) - 1} more)"
                            if user_message_missing:
                                await _toast(page, "Your message didn't reach the model. Please try again.")
                            else:
                                await _toast(page, f"Workflow error: {err_msg}")

                    # Append assistant message as soon as we have content so it always appears (even if run is superseded)
                    display_content = result.get("content_for_display", content) or content
                    meta = {
                        "turn_id": turn_id,
                        "assistant": asst,
                        "source": "assistant_response",
                        "workflow_response": {"reply": content, "result_kind": result.get("kind")},
                        "parsed_edits": result.get("edits", []),
                        "apply": result.get("apply_result", {}),
                    }
                    if result.get("kind") == "parse_error":
                        meta["format_error"] = True
                    if follow_up_contexts_this_turn:
                        meta["follow_up_contexts"] = follow_up_contexts_this_turn
                    _append("assistant", display_content, meta=meta)

                    if not _is_current_run(token):
                        return
                    _set_inline_status(None)

                    apply_fn = apply_from_assistant if apply_from_assistant else set_graph
                    if result.get("kind") == "applied" and result.get("graph") is not None:
                        graph_to_apply = result["graph"]
                        _client_todo_supplements: list[str] = []
                        # Client-side todos: code-block task only if coding_is_allowed; import review always when applicable.
                        if isinstance(graph_to_apply, dict):
                            from gui.flet.chat_with_the_assistants.todo_list_manager import (
                                augment_graph_with_client_tasks,
                            )

                            graph_to_apply, extra_supp = augment_graph_with_client_tasks(
                                graph_to_apply,
                                result.get("edits") or [],
                                coding_is_allowed=get_coding_is_allowed(),
                            )
                            _client_todo_supplements.extend(extra_supp)
                        # Validate via ValidateGraphToApply workflow (not direct core); canvas expects ProcessGraph.
                        applied_ok = False
                        if isinstance(graph_to_apply, dict):
                            vg, v_err = validate_graph_to_apply_for_canvas(graph_to_apply)
                            if v_err or vg is None:
                                graph_to_apply = None
                                if _is_current_run(token):
                                    await _toast(
                                        page,
                                        f"Could not validate graph: {(v_err or '')[:120]}",
                                    )
                            else:
                                graph_to_apply = vg
                        if graph_to_apply is not None:
                            apply_fn(graph_to_apply)
                            # Sync last_apply_result (and downstream prompts) with canvas graph, including client-side todo injections.
                            last_apply_result_ref[0] = refresh_last_apply_result_after_canvas_apply(
                                last_apply_result_ref[0],
                                graph_ref[0],
                                supplement_summary="; ".join(_client_todo_supplements),
                            )
                            await _toast(page, "Applied")
                            applied_graph = graph_to_apply
                            applied_ok = True
                        if applied_ok:
                            had_import_workflow = any(
                                e.get("action") == "import_workflow"
                                for e in result.get("edits", [])
                            )
                            _TODO_ACTIONS = frozenset({"add_todo_list", "remove_todo_list", "add_task", "remove_task", "mark_completed"})
                            had_todo = any(e.get("action") in _TODO_ACTIONS for e in result.get("edits", []))
                            had_add_comment = any(e.get("action") == "add_comment" for e in result.get("edits", []))
                            content_holder = [content]
                            post_ctx = PostApplyFollowUpContext(
                                graph_ref=graph_ref,
                                state=state,
                                token=token,
                                turn_id=turn_id,
                                assistant_label=asst,
                                max_rounds=max_wd_follow_ups,
                                wf_language_hint=wf_lang_cell,
                                is_current_run=_is_current_run,
                                toast=lambda m: _toast(page, m),
                                set_inline_status=_set_inline_status,
                                append_message=_append,
                                prepare_stream_row=_prepare_stream_row,
                                normalize_user_message_for_workflow=normalize_user_message_for_workflow,
                                last_apply_result_ref=last_apply_result_ref,
                                get_recent_changes=get_recent_changes,
                                overrides=overrides,
                                run_workflow_streaming=_run_workflow_with_streaming,
                                get_runtime_for_prompts=get_runtime_for_prompts,
                                format_previous_turn=format_previous_turn,
                                replace_assistant_message_row=_replace_assistant_message_row,
                                stream_buffer_ref=stream_buffer_ref,
                                apply_fn=apply_fn,
                            )
                            await run_post_apply_follow_up_rounds(
                                post_ctx,
                                result=result,
                                content_holder=content_holder,
                                parser_chain_runner=_parser_output_follow_up_chain,
                                flags=PostApplyFlags(
                                    had_import_workflow=had_import_workflow,
                                    had_todo=had_todo,
                                    had_add_comment=had_add_comment,
                                ),
                            )
                            content = content_holder[0]
                    elif result.get("kind") == "apply_failed":
                        # Ensure last_apply_result is stored so next turn (and same-turn retry) get self-correction block
                        failed_apply = result.get("last_apply_result") or result.get("apply_result") or {}
                        last_apply_result_ref[0] = failed_apply
                        err_str = str(failed_apply.get("error", "Unknown"))[:500]
                        await _toast(
                            page,
                            f"Could not apply edits: {err_str[:120]}",
                        )
                        # Same-turn self-correction: workflow_designer_handler builds retry inputs; we run and apply/toast
                        if _is_current_run(token):
                            _set_inline_status("Retrying with error context…")
                            try:
                                _graph = graph_ref[0]
                                retry_inputs = build_self_correction_retry_inputs(
                                    last_apply_result_ref[0],
                                    _graph,
                                    get_recent_changes() if get_recent_changes else None,
                                    runtime=get_runtime_for_prompts(_graph),
                                    coding_is_allowed=get_coding_is_allowed(),
                                    previous_turn=format_previous_turn(state.history),
                                    language_hint=wf_lang_cell[0],
                                    session_language=state.session_language,
                                )
                                _prepare_stream_row()
                                retry_response = await _run_workflow_with_streaming(
                                    run_assistant_workflow,
                                    retry_inputs,
                                    overrides,
                                    None,
                                )
                                maybe_pin_session_language_from_workflow_response(state, retry_response)
                                wf_lang_cell[0] = default_wf_language_hint(state.session_language)
                                if not _is_current_run(token):
                                    return
                                r_result = (retry_response.get("result") or {})
                                r_kind = r_result.get("kind")
                                if r_kind == "applied" and r_result.get("graph") is not None:
                                    graph_to_apply = r_result["graph"]
                                    if isinstance(graph_to_apply, dict):
                                        from gui.flet.chat_with_the_assistants.todo_list_manager import (
                                            augment_graph_with_client_tasks,
                                        )

                                        graph_to_apply, _retry_supp = augment_graph_with_client_tasks(
                                            graph_to_apply,
                                            r_result.get("edits") or [],
                                            coding_is_allowed=get_coding_is_allowed(),
                                        )
                                        vg, v_err = validate_graph_to_apply_for_canvas(graph_to_apply)
                                        if v_err or vg is None:
                                            graph_to_apply = None
                                            if _is_current_run(token):
                                                await _toast(
                                                    page,
                                                    f"Retry graph validation failed: {(v_err or '')[:100]}",
                                                )
                                        else:
                                            graph_to_apply = vg
                                    if graph_to_apply is not None:
                                        apply_fn(graph_to_apply)
                                        await _toast(page, "Applied (after retry)")
                                        retry_reply = (retry_response.get("reply") or "").strip()
                                        if retry_reply:
                                            content = content + "\n\n" + retry_reply
                                            result["content_for_display"] = content
                                            _append("assistant", retry_reply, meta={"turn_id": turn_id, "assistant": asst, "source": "assistant_response", "workflow_response": {"reply": retry_reply, "result_kind": "applied"}})
                                        last_apply_result_ref[0] = r_result.get("last_apply_result")
                                elif r_kind == "apply_failed":
                                    last_apply_result_ref[0] = r_result.get("last_apply_result") or r_result.get("apply_result")
                                    await _toast(page, f"Retry also failed: {str(r_result.get('apply_result', {}).get('error', 'Unknown'))[:80]}")
                            except Exception:
                                pass
                            _set_inline_status(None)
                    finalize_workflow_designer_turn_session_language(
                        state, response, debug_log=_workflow_debug_log
                    )
                    _persist_history()
                    return

                # RL Coach: run rl_coach_workflow.json (Inject→RAG→Aggregate→Prompt→LLM; same pattern as Workflow Designer).
                training_config_summary = await asyncio.to_thread(get_training_config_summary)
                training_results = get_training_results_follow_up()
                previous_turn = format_previous_turn(state.history[:-1])
                training_config_dict = await asyncio.to_thread(get_training_config_dict)
                initial_inputs = build_rl_coach_initial_inputs(
                    message_for_workflow,
                    training_config=training_config_summary,
                    training_results=training_results,
                    previous_turn=previous_turn,
                    training_config_dict=training_config_dict,
                )
                overrides = build_rl_coach_unit_param_overrides(
                    provider,
                    cfg,
                    rag_persist_dir=get_rag_index_dir(),
                    rag_embedding_model=get_rag_embedding_model(),
                )
                _prepare_stream_row()
                try:
                    response = await _run_workflow_with_streaming(
                        run_rl_coach_workflow,
                        initial_inputs,
                        overrides,
                        None,
                    )
                except WorkflowTimeoutError as ex:
                    _set_inline_status(None)
                    content = f"(Request timed out after {getattr(ex, 'timeout_s', 300):.0f}s. Try again.)"
                    response = {"reply": content, "workflow_errors": []}
                raw = (response.get("reply") or "").strip() or "(No response from model.)"
                _clear_stream_row()
                _set_inline_status(None)
                workflow_errors = response.get("workflow_errors") or []
                if workflow_errors and _is_current_run(token):
                    await _toast(page, f"Workflow error: {workflow_errors[0][1][:120]}")
                _append(
                    "assistant",
                    raw,
                    meta={
                        "turn_id": turn_id,
                        "assistant": asst,
                        "source": "assistant_response",
                        "workflow_response": {"reply": raw},
                    },
                )
                applied_config = response.get("applied_config")
                if applied_config and _is_current_run(token):
                    try:
                        import yaml
                        from gui.flet.components.settings import get_training_config_path, REPO_ROOT
                        path_str = (get_training_config_path() or "").strip()
                        if path_str:
                            path = Path(path_str)
                            if not path.is_absolute() and REPO_ROOT is not None:
                                path = (REPO_ROOT / path_str).resolve()
                            path.parent.mkdir(parents=True, exist_ok=True)
                            with path.open("w", encoding="utf-8") as f:
                                yaml.dump(applied_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                            await _toast(page, "Training config updated and saved.")
                    except Exception:
                        if _is_current_run(token):
                            await _toast(page, "Config was applied but save to file failed.")
                elif _is_current_run(token):
                    await _toast(page, "RL Coach reply.")
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

        page.run_task(_run)

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

