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
from typing import Any, Callable, Literal

import flet as ft

from assistants.process_assistant import process_assistant_apply
from assistants.prompts import RL_COACH_SYSTEM, WORKFLOW_DESIGNER_SYSTEM
from schemas.process_graph import ProcessGraph

from LLM_integrations import ollama as ollama_integration
from gui.flet.components.settings import get_chat_history_dir, get_ollama_host, get_ollama_model
from gui.flet.tools.notifications import show_toast

from gui.flet.chat_with_the_assistants.history_store import (
    list_recent_chat_files,
    load_chat_payload,
    slugify_filename,
    unique_path,
    write_chat_payload,
)
from gui.flet.chat_with_the_assistants.llm_client import suggest_chat_filename_base
from gui.flet.chat_with_the_assistants.message_renderer import build_message_row, render_messages
from gui.flet.chat_with_the_assistants.state import ChatSessionState


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


def _parse_json_block(content: str) -> dict[str, Any] | None:
    """Extract JSON object from LLM response. Prefer ```json ... ```; else first balanced {...}."""
    content = content.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if match:
        raw = match.group(1).strip()
    else:
        start = content.find("{")
        if start == -1:
            return None
        depth = 0
        end = start
        for i, ch in enumerate(content[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if depth != 0:
            return None
        raw = content[start : end + 1]
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


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

    state = ChatSessionState(
        history=[],
        busy=False,
        has_sent_any=False,
        session_id=_new_id(),
        created_at=_now_ts(),
        chat_path=None,
    )

    # --- Chat history persistence (auto-save) ---
    chat_history_dir = get_chat_history_dir()
    chat_history_dir.mkdir(parents=True, exist_ok=True)

    # Chat header shown inside the scroll area (top of messages column).
    # Style/position matches the old "Talk to..." helper text.
    chat_title_txt = ft.Text("new_chat", size=12, color=ft.Colors.GREY_500)

    messages_col = ft.Column(
        [chat_title_txt],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=8,
    )

    def _set_chat_title(title: str) -> None:
        chat_title_txt.value = title or "new_chat"
        try:
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
        payload = {
            "schema_version": CHAT_HISTORY_SCHEMA_VERSION,
            "session_id": state.session_id,
            "created_at": state.created_at,
            "assistant_selected": assistant_dd.value,
            "ollama": {"host": get_ollama_host(), "model": get_ollama_model()},
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
        _refresh_history_options()
        _set_history_dropdown_value(tmp.name)
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
                host = get_ollama_host()
                model = get_ollama_model()
                resp = await asyncio.to_thread(
                    lambda: suggest_chat_filename_base(
                        first_message=first_message,
                        host=host,
                        model=model,
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
                    _refresh_history_options()
                    _set_history_dropdown_value(new_path.name)
                    _persist_history()
            except OSError:
                pass

        page.run_task(_run)

    def _toast_now(msg: str) -> None:
        async def _run_toast() -> None:
            await _toast(page, msg)

        page.run_task(_run_toast)

    def _row_builder(msg: dict[str, Any]) -> ft.Row:
        return build_message_row(page=page, msg=msg, persist=_persist_history, toast=_toast_now, now_ts=_now_ts, bubble_width=420)

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

    # --- Recent chat history picker (load/continue) ---
    history_file_map: dict[str, Path] = {}
    _setting_history_value: list[bool] = [False]

    def _set_history_dropdown_value(filename: str | None) -> None:
        _setting_history_value[0] = True
        try:
            history_dd_top.value = filename
            history_dd_bottom.value = filename
            history_dd_top.update()
            history_dd_bottom.update()
        except Exception:
            pass
        finally:
            _setting_history_value[0] = False

    def _refresh_history_options(_e: ft.ControlEvent | None = None) -> None:
        files = list_recent_chat_files(chat_history_dir, limit=30)
        history_file_map.clear()
        for p in files:
            history_file_map[p.name] = p
        opts = [ft.dropdown.Option(name) for name in history_file_map.keys()]

        try:
            history_dd_top.options = opts
            history_dd_bottom.options = opts
            # Clear selection if it no longer exists
            if history_dd_top.value and history_dd_top.value not in history_file_map:
                _set_history_dropdown_value(None)
            history_dd_top.update()
            history_dd_bottom.update()
        except Exception:
            pass

    def _load_chat_file(path: Path) -> None:
        if state.busy:
            return
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

        _render_messages_from_history()
        _set_history_dropdown_value(path.name)

        try:
            top_input_container.update()
            bottom_input_row.update()
            history_row_top.update()
            history_row_bottom.update()
            page.update()
        except Exception:
            pass

    def _on_history_change(dd: ft.Dropdown) -> None:
        if _setting_history_value[0]:
            return
        val = dd.value
        if not val:
            return
        p = history_file_map.get(str(val))
        if p is None:
            _refresh_history_options()
            return
        _load_chat_file(p)

    history_dd_top = ft.Dropdown(
        value=None,
        width=240,
        height=32,
        text_style=ft.TextStyle(size=11),
        hint_text="Recent chats",
        options=[],
    )
    history_dd_bottom = ft.Dropdown(
        value=None,
        width=240,
        height=32,
        text_style=ft.TextStyle(size=11),
        hint_text="Recent chats",
        options=[],
    )
    # Some Flet versions don't accept on_change in the constructor
    history_dd_top.on_change = lambda _e: _on_history_change(history_dd_top)
    history_dd_bottom.on_change = lambda _e: _on_history_change(history_dd_bottom)

    history_row_top = ft.Row(
        [
            history_dd_top,
            ft.IconButton(icon=ft.Icons.REFRESH, icon_size=16, tooltip="Refresh", on_click=_refresh_history_options),
        ],
        spacing=0,
        visible=True,
    )
    history_row_bottom = ft.Row(
        [
            history_dd_bottom,
            ft.IconButton(icon=ft.Icons.REFRESH, icon_size=16, tooltip="Refresh", on_click=_refresh_history_options),
        ],
        spacing=0,
        visible=False,
    )

    def _set_busy(v: bool) -> None:
        state.busy = v
        input_tf_first.disabled = v
        input_tf.disabled = v
        input_tf_first.update()
        input_tf.update()
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
        history_row_top.visible = False
        history_row_bottom.visible = True
        top_input_container.update()
        bottom_input_row.update()
        history_row_top.update()
        history_row_bottom.update()
        page.update()

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
        _after_first_send()
        _set_busy(True)

        async def _run() -> None:
            try:
                asst: AssistantType = (assistant_dd.value or "Workflow Designer")  # type: ignore[assignment]
                host = get_ollama_host()
                model = get_ollama_model()
                options = {"temperature": 0.3, "num_predict": OLLAMA_NUM_PREDICT}

                if asst == "Workflow Designer":
                    ctx = json.dumps(_graph_summary(graph_ref[0]), indent=2)
                    user_with_ctx = f"Current process graph (summary):\n{ctx}\n\nUser request: {text}"
                    msgs: list[dict[str, str]] = [{"role": "system", "content": WORKFLOW_DESIGNER_SYSTEM}]
                    msgs.extend(_messages_from_history(state.history))
                    msgs.append({"role": "user", "content": user_with_ctx})

                    def _call() -> str:
                        return ollama_integration.chat(
                            host=host,
                            model=model,
                            messages=msgs,
                            timeout_s=OLLAMA_TIMEOUT_S,
                            options=options,
                        )

                    content = await asyncio.to_thread(_call)
                    if not content:
                        content = "(No response from model.)"
                    edit = _parse_json_block(content)
                    apply_result: dict[str, Any] = {"attempted": False, "success": None, "error": None}

                    # Apply edit if present and actionable
                    if isinstance(edit, dict) and edit.get("action") not in (None, "no_edit"):
                        apply_result["attempted"] = True
                        try:
                            new_graph = process_assistant_apply(graph_ref[0] or {"units": [], "connections": []}, edit)
                            set_graph(new_graph)
                            apply_result["success"] = True
                            await _toast(page, "Applied to graph")
                        except Exception as ex:
                            apply_result["success"] = False
                            apply_result["error"] = str(ex)[:500]
                            await _toast(page, f"Could not apply edit: {str(ex)[:120]}")

                    _append(
                        "assistant",
                        content,
                        meta={
                            "turn_id": turn_id,
                            "assistant": asst,
                            "source": "assistant_response",
                            "llm_request": {
                                "provider": "ollama",
                                "host": host,
                                "model": model,
                                "timeout_s": OLLAMA_TIMEOUT_S,
                                "options": options,
                                "messages": msgs,
                            },
                            "llm_response": {"raw": content},
                            "parsed_edit": edit,
                            "apply": apply_result,
                        },
                    )
                    return

                # RL Coach: training config not yet wired in Flet; still allow chat response without applying.
                msgs = [{"role": "system", "content": RL_COACH_SYSTEM}]
                msgs.extend(_messages_from_history(state.history))
                msgs.append({"role": "user", "content": text})

                def _call2() -> str:
                    return ollama_integration.chat(
                        host=host,
                        model=model,
                        messages=msgs,
                        timeout_s=OLLAMA_TIMEOUT_S,
                        options=options,
                    )

                content = await asyncio.to_thread(_call2)
                raw = content or "(No response from model.)"
                _append(
                    "assistant",
                    raw,
                    meta={
                        "turn_id": turn_id,
                        "assistant": asst,
                        "source": "assistant_response",
                        "llm_request": {
                            "provider": "ollama",
                            "host": host,
                            "model": model,
                            "timeout_s": OLLAMA_TIMEOUT_S,
                            "options": options,
                            "messages": msgs,
                        },
                        "llm_response": {"raw": raw},
                    },
                )
                await _toast(page, "RL Coach reply (not applied in Flet yet)")
            except ImportError as ex:
                _append(
                    "assistant",
                    str(ex),
                    meta={"turn_id": turn_id, "assistant": assistant_dd.value, "source": "error", "error_type": "ImportError"},
                )
            except Exception as ex:
                # Try to present nicer Ollama errors
                _append(
                    "assistant",
                    ollama_integration.format_ollama_exception(ex),
                    meta={"turn_id": turn_id, "assistant": assistant_dd.value, "source": "error", "error_type": type(ex).__name__},
                )
            finally:
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
        history_row_top.visible = True
        history_row_bottom.visible = False

        # Reset title
        _set_chat_title("new_chat")

        # Reset messages column (keep title at top)
        messages_col.controls = [chat_title_txt]

        # Reset history picker
        _refresh_history_options()
        _set_history_dropdown_value(None)

        # Best-effort refresh
        try:
            messages_col.update()
            top_input_container.update()
            bottom_input_row.update()
            history_row_top.update()
            history_row_bottom.update()
            input_tf_first.update()
            input_tf.update()
            page.update()
        except Exception:
            pass

    def _start_new_chat(_e: ft.ControlEvent) -> None:
        if state.busy:
            return
        _reset_chat_ui()

    # Populate recent chats on first render
    _refresh_history_options()

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
            top_input_container,
            history_row_top,
            ft.Container(content=messages_col, expand=True),
            bottom_input_row,
            history_row_bottom,
        ],
        expand=True,
        spacing=8,
    )

