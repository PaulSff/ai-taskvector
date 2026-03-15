"""
Flet assistants chat panel: Workflow Designer / RL Coach in the right column.

Chat always runs a workflow per assistant (no direct LLM path). Only the workflow file and handler differ.
- Workflow Designer: assistant_workflow.json; first message also runs create_filename.json for chat title.
- RL Coach: rl_coach_workflow.json.
"""
from __future__ import annotations

import asyncio
import json
import queue
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from typing import Any, Callable, Literal

import flet as ft

from units.canonical.process_agent import strip_json_blocks
from assistants.prompts import (
    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP,
    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP,
    WORKFLOW_DESIGNER_BROWSE_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_BROWSE_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP,
    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_TODO_FOLLOW_UP,
    WORKFLOW_DESIGNER_RAG_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_RAG_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_WEB_SEARCH_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_WEB_SEARCH_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_GREP_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_GREP_FOLLOW_UP_SUFFIX,
)

from core.normalizer.runtime_detector import is_canonical_runtime
from gui.flet.chat_with_the_assistants.rl_coach_handler import build_rl_coach_initial_inputs
from gui.flet.chat_with_the_assistants.workflow_designer_handler import (
    BROWSER_WORKFLOW_PATH,
    WEB_SEARCH_WORKFLOW_PATH,
    build_assistant_workflow_initial_inputs,
    build_assistant_workflow_unit_param_overrides,
    build_rl_coach_unit_param_overrides,
    run_assistant_workflow,
    run_create_filename_workflow,
    run_current_graph,
    run_rl_coach_workflow,
    run_workflow_with_errors,
)
from runtime.run import WorkflowTimeoutError
from units.web import register_web_units
from core.schemas.process_graph import ProcessGraph

from LLM_integrations import client as llm_client
from gui.flet.components.settings import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    get_coding_is_allowed,
    get_chat_history_dir,
    get_llm_provider,
    get_llm_provider_config,
    get_mydata_dir,
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
from gui.flet.chat_with_the_assistants.load_chat_history import load_chat_session
from gui.flet.chat_with_the_assistants.message_renderer import build_message_row, render_messages
from gui.flet.chat_with_the_assistants.rag_context import (
    _UNITS_DIR,
    get_rag_context,
    get_rag_context_by_path,
)
from gui.flet.chat_with_the_assistants.recent_chats_menu import RecentChatsMenu
from gui.flet.chat_with_the_assistants.status_bar import StatusBarController
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


def _normalize_user_message_for_workflow(raw: Any) -> str:
    """Ensure the user message is a proper string for the workflow (inject_user_message.data)."""
    if raw is None:
        return "(No message provided.)"
    s = raw if isinstance(raw, str) else str(raw)
    # Strip and remove null bytes / control chars that can break downstream
    s = s.replace("\x00", "").strip()
    return s if s else "(No message provided.)"


def _get_runtime_for_prompts(graph: Any) -> Literal["native", "external"]:
    """Read runtime from graph (set on import); fallback to is_canonical_runtime when missing."""
    if graph is None:
        return "external"
    r = graph.get("runtime") if isinstance(graph, dict) else getattr(graph, "runtime", None)
    if r in ("native", "external"):
        return r
    return "native" if is_canonical_runtime(graph) else "external"


def _messages_from_history(
    history: list[dict[str, Any]],
    *,
    max_turn_pairs: int = 10,
) -> list[dict[str, str]]:
    """Convert local history to LLM messages (role/content)."""
    out: list[dict[str, str]] = []

    cap = max_turn_pairs * 2
    msgs = history[-cap:] if len(history) > cap else history

    for m in msgs:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue

        raw_content = m.get("content")
        if not isinstance(raw_content, str):
            continue

        content = strip_json_blocks(raw_content)
        if not content:
            # Keep assistant turn so the model sees it already responded (avoids repeating the same edit on next turn)
            if role == "assistant":
                content = "(Previous response contained graph edits that were applied.)"
            else:
                continue

        out.append({"role": role, "content": content})


    return out


def _format_previous_turn(history: list[dict[str, Any]]) -> str:
    """
    Format the last complete turn (last user + last assistant) for the workflow.
    Includes any follow_up_context (RAG, web search, etc.) stored in the assistant message meta
    so the model sees that context on the next turn.
    Returns "" if there is no complete previous turn.
    """
    if not history or len(history) < 2:
        return ""
    # Find last assistant message, then the user message immediately before it
    last_assistant: dict[str, Any] | None = None
    last_user_before: dict[str, Any] | None = None
    for m in reversed(history):
        role = (m.get("role") or "").strip().lower()
        if role == "assistant" and last_assistant is None:
            last_assistant = m
        elif role == "user" and last_assistant is not None and last_user_before is None:
            last_user_before = m
            break
    if last_user_before is None or last_assistant is None:
        return ""
    user_content = (last_user_before.get("content") or last_user_before.get("content_for_display") or "")
    if not isinstance(user_content, str):
        user_content = str(user_content or "")
    user_content = strip_json_blocks(user_content).strip() or "(no message)"
    asst_content = (last_assistant.get("content") or last_assistant.get("content_for_display") or "")
    if not isinstance(asst_content, str):
        asst_content = str(asst_content or "")
    asst_content = strip_json_blocks(asst_content).strip() or "(no response)"
    # Prepend context used in that turn (RAG, web search, etc.) if stored in meta
    follow_ups = last_assistant.get("follow_up_contexts") or (last_assistant.get("meta") or {}).get("follow_up_contexts")
    if isinstance(follow_ups, list) and follow_ups:
        context_block = "Context used in that turn:\n" + "\n\n".join(str(c).strip() for c in follow_ups if c)
        asst_content = context_block + "\n\n--- My response ---\n\n" + asst_content
    return f"User: {user_content}\n\nAssistant: {asst_content}"


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

    # Stores last workflow apply result for grounding
    last_apply_result_ref: list[dict[str, Any] | None] = [None]

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
        if state.chat_path is None:
            return
        payload = build_chat_payload(
            schema_version=CHAT_HISTORY_SCHEMA_VERSION,
            session_id=state.session_id,
            created_at=state.created_at,
            assistant_selected=assistant_dd.value,
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
        row = _row_builder(msg)
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
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border_radius=8,
            bgcolor=ft.Colors.TRANSPARENT,
            expand=True,
        )
        # Align like assistant bubbles (left, with slight indent)
        row = ft.Row([ft.Container(expand=True, content=bubble, padding=ft.Padding.only(left=12))])
        stream_row_ref[0] = row
        messages_col.controls.append(row)
        safe_update(messages_col)
        safe_page_update(page)
        return txt

    def _prepare_stream_row() -> None:
        """Show the streaming bubble before the model runs, so tokens appear as they generate."""
        txt = _ensure_stream_row()
        txt.value = ""
        safe_update(txt)
        safe_page_update(page)

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
                stream_txt = _ensure_stream_row()
                stream_txt.value = (stream_txt.value or "") + piece
                safe_update(stream_txt)
                safe_page_update(page)
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
        focus_pref[0] = "bottom" if state.has_sent_any else "first"
        _schedule_restore_focus()

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
    history_row_top_with_model = ft.Row(
        [
            history_row_top,
            ft.Container(expand=True),
            model_label_top,
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        visible=history_row_top.visible,
    )
    top_wrapper_row_ref[0] = history_row_top_with_model
    history_row_with_model = ft.Row(
        [
            history_row_bottom,
            ft.Container(expand=True),
            model_label,
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        visible=history_row_bottom.visible,
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
        if show_run_current_graph:
            run_current_graph_cb.disabled = v
            run_current_graph_cb.update()
        input_tf_first.update()
        input_tf.update()
        if not v:
            _set_inline_status(None)
            _clear_stream_row()
        status_bar.set_stop_visible(bool(v))
        page.update()

    # Toggle input placement: top (first message) -> bottom (subsequent)
    top_input_container = ft.Container(content=input_tf_first, visible=True)
    run_current_graph_cb = ft.Checkbox(label="Run current graph", value=False, tooltip="(-dev) Execute the current workflow with this message instead of assistant_workflow.json")
    bottom_input_row_controls: list[ft.Control] = [input_tf]
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
        focus_pref[0] = "bottom"
        if recent_menu_ref[0] is not None:
            recent_menu_ref[0].set_phase(has_sent_any=True)
        safe_update(top_input_container, bottom_input_row, history_row_top_with_model, history_row_with_model, chat_title_top_txt, chat_title_txt)
        safe_page_update(page)

    def _send_from_field(field: ft.TextField) -> None:
        text = (field.value or "").strip()
        if not text or state.busy:
            return
        # Capture message for workflow at send time so it is never lost (used as inject_user_message.data).
        message_for_workflow = _normalize_user_message_for_workflow(text)
        field.value = ""
        field.update()
        turn_id = _new_id()
        # On first message only: two parallel requests. (1) Title: direct LLM call (bypasses workflow).
        # (2) Chat response: same message goes through assistant_workflow.json in _run() below.
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
                    # Workflow-driven: run assistant_workflow.json, consume merge_response.data. Phase 2: follow-up loop (file/RAG/web/browse/code_block) with statuses.
                    overrides = build_assistant_workflow_unit_param_overrides(
                        provider,
                        cfg,
                        str(get_rag_index_dir()),
                        get_rag_embedding_model(),
                        report_output_dir=str(Path(get_mydata_dir()) / "reports"),
                    )
                    _set_inline_status("Thinking…")
                    follow_up_contexts_this_turn: list[str] = []
                    try:
                        # Show streaming bubble immediately so user sees tokens as they generate.
                        _prepare_stream_row()
                        # Use last user message from history as source of truth so the model always gets what was actually sent (avoids closure/async losing the message).
                        last_user_content = None
                        for m in reversed(state.history or []):
                            if isinstance(m, dict) and (m.get("role") or "").strip().lower() == "user":
                                last_user_content = (m.get("content") or m.get("content_for_display") or "")
                                break
                        user_message_for_workflow = _normalize_user_message_for_workflow(
                            last_user_content if (last_user_content is not None and str(last_user_content).strip()) else message_for_workflow
                        )
                        _graph = graph_ref[0]
                        _runtime = _get_runtime_for_prompts(_graph)
                        initial_inputs = build_assistant_workflow_initial_inputs(
                            user_message_for_workflow,
                            _graph,
                            last_apply_result_ref[0],
                            get_recent_changes() if get_recent_changes else None,
                            runtime=_runtime,
                            coding_is_allowed=get_coding_is_allowed(),
                            previous_turn=_format_previous_turn(state.history[:-1]),
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
                        # Follow-up loop: if parser_output requests file/RAG/web/browse/code_block, fetch and re-run (max 5).
                        MAX_FOLLOW_UPS = 5
                        for _ in range(MAX_FOLLOW_UPS):
                            po = response.get("parser_output")
                            if not isinstance(po, dict):
                                break
                            follow_up_context: str | None = None
                            follow_up_msg = WORKFLOW_DESIGNER_FOLLOW_UP_USER_MESSAGE
                            if po.get("run_workflow"):
                                _set_inline_status("Workflow run result…")
                                run_out = response.get("run_output")
                                if isinstance(run_out, dict):
                                    data = run_out.get("data")
                                    err = run_out.get("error")
                                    parts = []
                                    if data is not None:
                                        try:
                                            parts.append(json.dumps(data, indent=2))
                                        except Exception:
                                            parts.append(str(data))
                                    if isinstance(err, str) and err.strip():
                                        parts.append(f"Error: {err}")
                                    if parts:
                                        follow_up_context = WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_PREFIX + "\n".join(parts) + WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_SUFFIX
                                elif run_out is not None:
                                    follow_up_context = WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_PREFIX + str(run_out) + WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_SUFFIX
                            elif po.get("grep"):
                                _set_inline_status("Grep result…")
                                grep_out = response.get("grep_output")
                                text = ""
                                if isinstance(grep_out, dict):
                                    text = (grep_out.get("out") or grep_out.get("data") or "").strip()
                                    err = grep_out.get("error")
                                    if isinstance(err, str) and err.strip():
                                        text = f"{text}\nError: {err}".strip() if text else f"Error: {err}"
                                elif grep_out is not None:
                                    text = str(grep_out).strip()
                                if text:
                                    follow_up_context = WORKFLOW_DESIGNER_GREP_FOLLOW_UP_PREFIX + text + WORKFLOW_DESIGNER_GREP_FOLLOW_UP_SUFFIX
                            elif po.get("read_file"):
                                _set_inline_status("Reading file…")
                                parts = []
                                for path in po.get("read_file") or []:
                                    c = await asyncio.to_thread(
                                        get_rag_context_by_path,
                                        path,
                                        "Workflow Designer",
                                    )
                                    if c and c.strip():
                                        parts.append(f"--- {path} ---\n{c.strip()}")
                                if parts:
                                    follow_up_context = WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX + "\n\n".join(parts) + WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX
                            elif po.get("rag_search"):
                                _set_inline_status("Searching knowledge base…")
                                rag_ctx = await asyncio.to_thread(
                                    get_rag_context,
                                    po["rag_search"],
                                    "Workflow Designer",
                                    po.get("rag_search_max_results"),
                                    po.get("rag_search_max_chars"),
                                    po.get("rag_search_snippet_max"),
                                )
                                if rag_ctx and rag_ctx.strip():
                                    follow_up_context = WORKFLOW_DESIGNER_RAG_FOLLOW_UP_PREFIX + rag_ctx.strip() + WORKFLOW_DESIGNER_RAG_FOLLOW_UP_SUFFIX
                            elif po.get("web_search"):
                                _set_inline_status("Searching web…")
                                try:
                                    register_web_units()
                                    out, errs = run_workflow_with_errors(
                                        WEB_SEARCH_WORKFLOW_PATH,
                                        initial_inputs={"inject_query": {"data": po["web_search"]}},
                                        unit_param_overrides={"web_search": {"max_results": po.get("web_search_max_results", 10)}},
                                        format="dict",
                                    )
                                    if errs and _is_current_run(token):
                                        await _toast(page, f"Web search error: {errs[0][1][:120]}")
                                    res = (out.get("web_search") or {}).get("out") or ""
                                    if res:
                                        follow_up_context = WORKFLOW_DESIGNER_WEB_SEARCH_FOLLOW_UP_PREFIX + res + WORKFLOW_DESIGNER_WEB_SEARCH_FOLLOW_UP_SUFFIX
                                except Exception:
                                    pass
                            elif po.get("browse_url"):
                                _set_inline_status("Loading page…")
                                try:
                                    register_web_units()
                                    out, errs = run_workflow_with_errors(
                                        BROWSER_WORKFLOW_PATH,
                                        initial_inputs={"inject_url": {"data": po["browse_url"]}},
                                        format="dict",
                                    )
                                    if errs and _is_current_run(token):
                                        await _toast(page, f"Browse error: {errs[0][1][:120]}")
                                    res = (out.get("beautifulsoup") or {}).get("out") or ""
                                    if res:
                                        follow_up_context = WORKFLOW_DESIGNER_BROWSE_FOLLOW_UP_PREFIX + res + WORKFLOW_DESIGNER_BROWSE_FOLLOW_UP_SUFFIX
                                except Exception:
                                    pass
                            elif po.get("read_code_block_ids") and graph_ref[0]:
                                _set_inline_status("Loading code block…")
                                _graph = graph_ref[0]
                                if hasattr(_graph, "model_dump"):
                                    _graph = _graph.model_dump(by_alias=True)
                                blocks = (_graph or {}).get("code_blocks") or []
                                block_by_id = {str(b.get("id")): b for b in blocks if isinstance(b, dict) and b.get("id")}
                                parts = []
                                for bid in po.get("read_code_block_ids") or []:
                                    b = block_by_id.get(str(bid).strip())
                                    if b:
                                        parts.append(f"Code block for unit {bid} ({b.get('language', '?')}):\n\n{b.get('source') or ''}\n")
                                if parts:
                                    follow_up_context = WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_PREFIX + "\n".join(parts) + WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_SUFFIX
                                    ids = (po.get("read_code_block_ids") or [])
                                    follow_up_msg = WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_USER_MESSAGE.format(unit_ids=", ".join(str(x) for x in ids))
                            if not follow_up_context:
                                break
                            follow_up_contexts_this_turn.append(follow_up_context)
                            if not _is_current_run(token):
                                return
                            # Keep the previous turn's message (e.g. search JSON) before we overwrite response with the follow-up run.
                            prev_reply = response.get("reply")
                            prev_content = (
                                prev_reply.get("action")
                                if isinstance(prev_reply, dict) and "action" in prev_reply
                                else (prev_reply if isinstance(prev_reply, str) else str(prev_reply or ""))
                            )
                            prev_content = (prev_content or "").strip()
                            if prev_content:
                                _append(
                                    "assistant",
                                    prev_content,
                                    meta={
                                        "turn_id": turn_id,
                                        "assistant": asst,
                                        "source": "assistant_response",
                                        "workflow_response": {"reply": prev_content},
                                    },
                                )
                            # Show streaming bubble for follow-up run so user sees tokens as they generate.
                            _prepare_stream_row()
                            # Follow-up: use constant user message (or code-block-specific with unit_ids); skip RAG in workflow (context is in follow_up_context).
                            follow_up_msg = _normalize_user_message_for_workflow(follow_up_msg)
                            _graph = graph_ref[0]
                            _runtime = _get_runtime_for_prompts(_graph)
                            initial_inputs = build_assistant_workflow_initial_inputs(
                                follow_up_msg,
                                _graph,
                                last_apply_result_ref[0],
                                get_recent_changes() if get_recent_changes else None,
                                follow_up_context,
                                runtime=_runtime,
                                coding_is_allowed=get_coding_is_allowed(),
                            )
                            follow_up_overrides = {
                                **overrides,
                                "rag_search": {**(overrides.get("rag_search") or {}), "ignore": True},
                            }
                            response = await _run_workflow_with_streaming(
                                run_assistant_workflow,
                                initial_inputs,
                                follow_up_overrides,
                                None,
                            )
                            if not _is_current_run(token):
                                return

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
                        result["apply_result"] = response.get("status") or wf_result.get("last_apply_result") or {}
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
                        # Workflow returns graph as dict (from ApplyEdits); canvas expects ProcessGraph (has .layout).
                        if isinstance(graph_to_apply, dict):
                            graph_to_apply = ProcessGraph.model_validate(graph_to_apply)
                        apply_fn(graph_to_apply)
                        await _toast(page, "Applied")
                        applied_graph = graph_to_apply
                        had_import_workflow = any(
                            e.get("action") == "import_workflow"
                            for e in result.get("edits", [])
                        )
                        _TODO_ACTIONS = frozenset({"add_todo_list", "remove_todo_list", "add_task", "remove_task", "mark_completed"})
                        had_todo = any(e.get("action") in _TODO_ACTIONS for e in result.get("edits", []))
                        had_add_comment = any(e.get("action") == "add_comment" for e in result.get("edits", []))
                        # Post-apply follow-up: one extra run with import/comment/todo message so model can add a short reply.
                        if had_import_workflow or had_add_comment or had_todo:
                            if had_import_workflow:
                                post_msg = WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP
                            elif had_add_comment and had_todo:
                                post_msg = WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP
                            elif had_add_comment:
                                post_msg = WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP
                            else:
                                post_msg = WORKFLOW_DESIGNER_TODO_FOLLOW_UP
                            if _is_current_run(token):
                                _set_inline_status("Continuing…")
                                try:
                                    _prepare_stream_row()
                                    # Use constant user message for all post-apply follow-ups (same pattern as RAG/search follow-up).
                                    if had_import_workflow:
                                        post_user_msg = _normalize_user_message_for_workflow(WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP_USER_MESSAGE)
                                    elif had_add_comment and had_todo:
                                        post_user_msg = _normalize_user_message_for_workflow(WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP_USER_MESSAGE)
                                    elif had_add_comment:
                                        post_user_msg = _normalize_user_message_for_workflow(WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP_USER_MESSAGE)
                                    else:
                                        post_user_msg = _normalize_user_message_for_workflow(WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE)
                                    _graph = graph_ref[0]
                                    _runtime = _get_runtime_for_prompts(_graph)
                                    post_inputs = build_assistant_workflow_initial_inputs(
                                        post_user_msg,
                                        _graph,
                                        last_apply_result_ref[0],
                                        get_recent_changes() if get_recent_changes else None,
                                        post_msg,
                                        runtime=_runtime,
                                        coding_is_allowed=get_coding_is_allowed(),
                                    )
                                    post_response = await _run_workflow_with_streaming(
                                        run_assistant_workflow,
                                        post_inputs,
                                        overrides,
                                        None,
                                    )
                                    post_reply = (post_response.get("reply") or "").strip()
                                    if post_reply:
                                        content = content + "\n\n" + post_reply
                                        result["content_for_display"] = content
                                    pw = post_response.get("result") or {}
                                    if pw.get("last_apply_result"):
                                        last_apply_result_ref[0] = pw["last_apply_result"]
                                    post_errors = post_response.get("workflow_errors") or []
                                    if post_errors and _is_current_run(token):
                                        await _toast(page, f"Workflow error: {post_errors[0][1][:120]}")
                                except Exception:
                                    pass
                                _set_inline_status(None)
                    elif result.get("kind") == "apply_failed":
                        await _toast(
                            page,
                            f"Could not apply edits: {str(result.get('apply_result', {}).get('error', 'Unknown'))[:120]}",
                        )
                    return

                # RL Coach: run rl_coach_workflow.json (same pattern as Workflow Designer, no direct LLM).
                rag_ctx = await asyncio.to_thread(get_rag_context, text, "RL Coach")
                initial_inputs = build_rl_coach_initial_inputs(text, rag_ctx or None)
                overrides = build_rl_coach_unit_param_overrides(provider, cfg)
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
            history_row_top_with_model,
            history_row_with_model,
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
            history_row_top_with_model,
            ft.Container(content=messages_col, expand=True),
            bottom_input_row,
            history_row_with_model,
        ],
        expand=True,
        spacing=8,
    )

