"""
Flet assistants chat panel: Workflow Designer / RL Coach in the right column.

Uses:
- assistants.prompts (system prompts)
- assistants.process_assistant (parse_workflow_edits, apply_workflow_edits, graph_summary)
- LLM_integrations.ollama (model API client)

This is the Flet equivalent of the Streamlit sketch in gui/app.py + gui/chat.py.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from threading import Thread
from typing import Any, Callable, Literal

import flet as ft

from assistants.llm_parsing import strip_json_blocks
from assistants.process_assistant import graph_summary, parse_workflow_edits
from assistants.prompts import (
    RL_COACH_SYSTEM,
    WORKFLOW_DESIGNER_RETRY_USER,
    WORKFLOW_DESIGNER_SELF_CORRECTION,
    WORKFLOW_DESIGNER_SYSTEM,
)

from gui.flet.chat_with_the_assistants.edit_actions_handler import run_workflow_designer_follow_ups
from gui.flet.chat_with_the_assistants.rl_coach_handler import build_rl_coach_messages
from gui.flet.chat_with_the_assistants.workflow_designer_handler import (
    build_workflow_designer_messages,
    build_workflow_designer_system_prompt,
    handle_workflow_edits_response,
)
from core.schemas.process_graph import ProcessGraph

from LLM_integrations import client as llm_client
from gui.flet.components.settings import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
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
from gui.flet.chat_with_the_assistants.llm_client import suggest_chat_filename_base
from gui.flet.chat_with_the_assistants.message_renderer import build_message_row, render_messages
from gui.flet.chat_with_the_assistants.rag_add_documents_dialog import open_rag_add_documents_dialog
from gui.flet.chat_with_the_assistants.rag_context import (
    _UNITS_DIR,
    get_rag_context,
    rag_query_from_graph_origin,
    read_file_content_for_assistant,
)


def _unit_docs_and_rag_sync(
    graph: Any,
    mydata_dir: Path,
    rag_index_dir: Path,
    units_dir: Path,
    embedding_model: str,
    llm_host: str,
    llm_model: str,
) -> int:
    """Run unit-doc augmenter then RAG update if any docs written. Returns number of units updated."""
    from rag.augmenter import ensure_unit_docs_for_units, graph_to_unit_identities
    from rag.context_updater import run_update

    identities = graph_to_unit_identities(graph, mydata_dir=mydata_dir)
    if not identities:
        return 0
    # Retrieve RAG context based on graph origin (Node-RED, n8n, canonical) to prompt the augmenter
    rag_context: str | None = None
    try:
        query = rag_query_from_graph_origin(graph)
        ctx = get_rag_context(query, "Workflow Designer")
        rag_context = ctx.strip() if (ctx and ctx.strip()) else None
    except Exception:
        rag_context = None
    count = ensure_unit_docs_for_units(
        identities,
        mydata_dir,
        llm_host=llm_host,
        llm_model=llm_model,
        units_dir=units_dir,
        rag_context=rag_context,
        graph=graph,
    )
    if count > 0:
        run_update(
            rag_index_dir,
            units_dir,
            mydata_dir,
            embedding_model=embedding_model,
        )
    return count


def _unit_docs_and_rag_sync_for_unit_ids(
    graph: Any,
    unit_ids: list[str],
    mydata_dir: Path,
    rag_index_dir: Path,
    units_dir: Path,
    embedding_model: str,
    llm_host: str,
    llm_model: str,
) -> int:
    """Run unit-doc augmenter only for the given unit ids, then RAG update. Returns number of units updated."""
    from rag.augmenter import ensure_unit_docs_for_units, identities_for_unit_ids
    from rag.context_updater import run_update

    identities = identities_for_unit_ids(graph, unit_ids, mydata_dir=mydata_dir)
    if not identities:
        return 0
    rag_context: str | None = None
    try:
        query = rag_query_from_graph_origin(graph)
        ctx = get_rag_context(query, "Workflow Designer")
        rag_context = ctx.strip() if (ctx and ctx.strip()) else None
    except Exception:
        rag_context = None
    count = ensure_unit_docs_for_units(
        identities,
        mydata_dir,
        llm_host=llm_host,
        llm_model=llm_model,
        units_dir=units_dir,
        rag_context=rag_context,
        graph=graph,
    )
    if count > 0:
        run_update(
            rag_index_dir,
            units_dir,
            mydata_dir,
            embedding_model=embedding_model,
        )
    return count
from gui.flet.chat_with_the_assistants.recent_chats_menu import RecentChatsMenu
from gui.flet.chat_with_the_assistants.status_bar import StatusBarController
from gui.flet.chat_with_the_assistants.state import ChatSessionState
from gui.flet.chat_with_the_assistants.ui_utils import safe_page_update, safe_update


AssistantType = Literal["Workflow Designer", "RL Coach"]

# Model options
OLLAMA_NUM_PREDICT = 1024
OLLAMA_TIMEOUT_S = 300
# Max automatic retries when apply fails (self-correction loop)
MAX_APPLY_RETRIES = 2

CHAT_HISTORY_SCHEMA_VERSION = 2

def _now_ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid4().hex


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
    show_rag_dev_tool: bool = False,
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
        input_tf_first.update()
        input_tf.update()
        if not v:
            _set_inline_status(None)
            _clear_stream_row()
        status_bar.set_stop_visible(bool(v))
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
        safe_update(top_input_container, bottom_input_row, history_row_top_with_model, history_row_with_model, chat_title_top_txt, chat_title_txt)
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
                    retry_count = 0
                    content = ""
                    msgs: list[dict[str, str]] = []
                    result: dict[str, Any] = {}

                    while True:
                        current_graph_summary = graph_summary(graph_ref[0])
                        recent_changes = get_recent_changes() if get_recent_changes else None
                        if retry_count == 0:
                            rag_ctx = await asyncio.to_thread(get_rag_context, text, "Workflow Designer")
                        else:
                            rag_ctx = None
                        system_content = build_workflow_designer_system_prompt(
                            current_graph_summary,
                            last_apply_result_ref[0],
                            base_prompt=WORKFLOW_DESIGNER_SYSTEM,
                            self_correction_template=WORKFLOW_DESIGNER_SELF_CORRECTION,
                            recent_changes=recent_changes,
                            rag_context=rag_ctx or None,
                        )
                        if retry_count == 0:
                            msgs = build_workflow_designer_messages(
                                system_content,
                                state.history[:-1],
                                text,
                                _messages_from_history,
                                max_turn_pairs=1,
                            )
                        else:
                            retry_user = WORKFLOW_DESIGNER_RETRY_USER.format(
                                error=result.get("apply_result", {}).get("error", "Unknown")
                            )
                            msgs = (
                                [{"role": "system", "content": system_content}]
                                + _messages_from_history(state.history[:-1], max_turn_pairs=1)
                                + [{"role": "user", "content": text}]
                                + [{"role": "assistant", "content": content}]
                                + [{"role": "user", "content": retry_user}]
                            )
                            _set_inline_status("Planning next move…")

                        q: asyncio.Queue[Any] = asyncio.Queue()
                        loop = asyncio.get_running_loop()

                        def _producer(msgs_to_send: list[dict[str, str]]) -> None:
                            try:
                                for piece in llm_client.chat_stream(
                                    provider=provider,
                                    config=cfg,
                                    messages=msgs_to_send,
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

                        Thread(target=_producer, args=(msgs,), daemon=True).start()

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

                        # Show "Searching..." while RAG query runs when assistant requested search
                        parse_preview = parse_workflow_edits(content)
                        if isinstance(parse_preview, dict) and parse_preview.get("rag_search"):
                            _set_inline_status("Searching knowledge base…")
                        else:
                            _set_inline_status("Applying edits…")
                        result = handle_workflow_edits_response(content, graph_ref[0])
                        last_apply_result_ref[0] = result["last_apply_result"]

                        async def _run_llm_for_follow_ups(msgs: list) -> str:
                            Thread(target=_producer, args=(msgs,), daemon=True).start()
                            content_parts = []
                            while True:
                                item = await q.get()
                                if item is None:
                                    break
                                if isinstance(item, Exception):
                                    raise item
                                if not _is_current_run(token):
                                    return ""
                                piece = str(item)
                                if piece:
                                    content_parts.append(piece)
                            return "".join(content_parts).strip() or "(No response.)"

                        apply_fn = apply_from_assistant if apply_from_assistant else set_graph
                        result, content = await run_workflow_designer_follow_ups(
                            result,
                            content,
                            get_graph=lambda: graph_ref[0],
                            user_message=text,
                            last_apply_result_ref=last_apply_result_ref,
                            run_llm=_run_llm_for_follow_ups,
                            get_history_messages=lambda: _messages_from_history(state.history[:-1], max_turn_pairs=1),
                            read_file=lambda path, md, ud, rr: read_file_content_for_assistant(path, md, ud, rr),
                            mydata_dir=get_mydata_dir(),
                            units_dir=_UNITS_DIR,
                            repo_root=_UNITS_DIR.parent,
                            set_status=_set_inline_status,
                            apply_fn=apply_fn,
                            is_cancelled=lambda: not _is_current_run(token),
                        )

                        if result["kind"] == "applied":
                            apply_fn(result["graph"])
                            await _toast(page, "Applied")
                            _set_inline_status(None)
                            requested_unit_specs = result.get("requested_unit_specs") or []
                            applied_graph = result["graph"]
                            had_import_workflow = any(
                                e.get("action") == "import_workflow"
                                for e in result.get("edits", [])
                            )
                            # Targeted: assistant asked for specs for specific units only
                            if requested_unit_specs:
                                _set_inline_status("Generating unit specs…")
                                async def _run_targeted_unit_docs() -> None:
                                    try:
                                        profile = _assistant_profile_key("Workflow Designer")
                                        cfg = get_llm_provider_config(assistant=profile)
                                        llm_host = (cfg.get("host") or DEFAULT_OLLAMA_HOST).strip()
                                        llm_model = (cfg.get("model") or DEFAULT_OLLAMA_MODEL).strip()
                                        count = await asyncio.to_thread(
                                            _unit_docs_and_rag_sync_for_unit_ids,
                                            applied_graph,
                                            requested_unit_specs,
                                            get_mydata_dir(),
                                            get_rag_index_dir(),
                                            _UNITS_DIR,
                                            get_rag_embedding_model(),
                                            llm_host,
                                            llm_model,
                                        )
                                        if count > 0:
                                            await _toast(page, "Unit specs updated")
                                    except Exception:
                                        pass
                                    finally:
                                        _set_inline_status(None)

                                asyncio.create_task(_run_targeted_unit_docs())
                            # Fallback: after import_workflow with no request_unit_specs, full augment in background
                            elif had_import_workflow:
                                async def _run_unit_docs_and_rag() -> None:
                                    try:
                                        profile = _assistant_profile_key("Workflow Designer")
                                        cfg = get_llm_provider_config(assistant=profile)
                                        llm_host = (cfg.get("host") or DEFAULT_OLLAMA_HOST).strip()
                                        llm_model = (cfg.get("model") or DEFAULT_OLLAMA_MODEL).strip()
                                        count = await asyncio.to_thread(
                                            _unit_docs_and_rag_sync,
                                            applied_graph,
                                            get_mydata_dir(),
                                            get_rag_index_dir(),
                                            _UNITS_DIR,
                                            get_rag_embedding_model(),
                                            llm_host,
                                            llm_model,
                                        )
                                        if count > 0:
                                            await _toast(page, "Unit docs updated")
                                    except Exception:
                                        pass

                                asyncio.create_task(_run_unit_docs_and_rag())
                            break
                        elif result["kind"] == "no_edits":
                            requested_unit_specs = result.get("requested_unit_specs") or []
                            if requested_unit_specs and graph_ref[0]:
                                _graph = graph_ref[0]
                                _set_inline_status("Generating unit specs…")
                                async def _run_targeted_unit_docs_no_edits() -> None:
                                    try:
                                        profile = _assistant_profile_key("Workflow Designer")
                                        cfg = get_llm_provider_config(assistant=profile)
                                        llm_host = (cfg.get("host") or DEFAULT_OLLAMA_HOST).strip()
                                        llm_model = (cfg.get("model") or DEFAULT_OLLAMA_MODEL).strip()
                                        count = await asyncio.to_thread(
                                            _unit_docs_and_rag_sync_for_unit_ids,
                                            _graph,
                                            requested_unit_specs,
                                            get_mydata_dir(),
                                            get_rag_index_dir(),
                                            _UNITS_DIR,
                                            get_rag_embedding_model(),
                                            llm_host,
                                            llm_model,
                                        )
                                        if count > 0:
                                            await _toast(page, "Unit specs updated")
                                    except Exception:
                                        pass
                                    finally:
                                        _set_inline_status(None)

                                asyncio.create_task(_run_targeted_unit_docs_no_edits())
                            else:
                                _set_inline_status(None)
                            break
                        elif retry_count < MAX_APPLY_RETRIES:
                            retry_count += 1
                            await _toast(page, "Retrying…")
                        else:
                            await _toast(
                                page,
                                f"Could not apply edits: {str(result.get('apply_result', {}).get('error', 'Unknown'))[:120]}",
                            )
                            _set_inline_status(None)
                            break

                    if not _is_current_run(token):
                        return
                    _set_inline_status(None)

                    meta: dict[str, Any] = {
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
                        "parsed_edits": result.get("edits", []),
                        "apply": result.get("apply_result", {}),
                    }
                    if result.get("kind") == "parse_error":
                        meta["format_error"] = True

                    _append("assistant", result.get("content_for_display", content) or content, meta=meta)
                    return

                # RL Coach: training config not yet wired in Flet; still allow chat response without applying.
                rag_ctx = await asyncio.to_thread(get_rag_context, text, "RL Coach")
                msgs = build_rl_coach_messages(
                    state.history[:-1],
                    text,
                    _messages_from_history,
                    system_prompt=RL_COACH_SYSTEM,
                    rag_context=rag_ctx or None,
                )

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

    # --- Dev: RAG context preview ---
    rag_preview_query = ft.TextField(
        hint_text="Query (e.g. user message)...",
        expand=True,
        height=36,
        text_style=ft.TextStyle(size=12),
        dense=True,
    )
    rag_preview_output = ft.TextField(
        read_only=True,
        multiline=True,
        min_lines=4,
        max_lines=12,
        expand=True,
        text_style=ft.TextStyle(size=11, font_family="monospace"),
        hint_text="RAG context will appear here after Preview.",
    )

    def _on_rag_preview_click(_e: ft.ControlEvent) -> None:
        query = (rag_preview_query.value or "").strip()
        assistant = (assistant_dd.value or "Workflow Designer").strip()
        if not query:
            rag_preview_output.value = "(Enter a query and click Preview.)"
            rag_preview_output.update()
            return
        rag_preview_output.value = "Loading..."
        rag_preview_output.update()

        async def _fetch() -> None:
            try:
                ctx = await asyncio.to_thread(get_rag_context, query, assistant)
                rag_preview_output.value = ctx if ctx else "(No RAG context returned.)"
            except Exception as ex:
                rag_preview_output.value = f"Error: {ex}"
            try:
                rag_preview_output.update()
            except Exception:
                pass

        page.run_task(_fetch)

    rag_preview_btn = ft.OutlinedButton("Preview", on_click=_on_rag_preview_click)
    dev_rag_section = ft.Container(
        content=ft.Column(
            [
                ft.Text("Dev: RAG context preview", size=11, color=ft.Colors.GREY_500),
                ft.Row([rag_preview_query, rag_preview_btn], spacing=8),
                ft.Container(content=rag_preview_output, height=160),
            ],
            spacing=6,
            tight=True,
        ),
        padding=ft.padding.symmetric(horizontal=8, vertical=6),
        border=ft.border.all(1, ft.Colors.GREY_700),
        border_radius=6,
        visible=show_rag_dev_tool,
    )

    return ft.Column(
        [
            ft.Row(
                [
                    ft.Icon(ft.Icons.SMART_TOY, size=30, color=ft.Colors.GREY_200),
                    ft.Container(expand=True),
                    ft.IconButton(
                        icon=ft.Icons.FOLDER_OPEN,
                        icon_size=18,
                        tooltip="Add documents to RAG",
                        on_click=lambda _: open_rag_add_documents_dialog(page),
                    ),
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
            dev_rag_section,
        ],
        expand=True,
        spacing=8,
    )

