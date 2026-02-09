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


AssistantType = Literal["Workflow Designer", "RL Coach"]

# Model options
OLLAMA_NUM_PREDICT = 1024
OLLAMA_TIMEOUT_S = 300

CHAT_HISTORY_SCHEMA_VERSION = 2


def _slugify_filename(text: str, *, max_len: int = 64) -> str:
    """
    Convert text to a safe snake_case-ish filename base (no extension).
    Fallback when LLM naming fails.
    """
    t = (text or "").strip().lower()
    t = re.sub(r"[^a-z0-9]+", "_", t)
    t = re.sub(r"_+", "_", t).strip("_")
    if not t:
        t = "chat"
    return t[:max_len].strip("_") or "chat"


def _unique_path(dir_path: Path, base: str) -> Path:
    """Return a unique path under dir_path for base.json (adds _2, _3...)."""
    p = dir_path / f"{base}.json"
    if not p.exists():
        return p
    i = 2
    while True:
        cand = dir_path / f"{base}_{i}.json"
        if not cand.exists():
            return cand
        i += 1


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

    history: list[dict[str, Any]] = []  # {role, content}
    busy: list[bool] = [False]
    has_sent_any: list[bool] = [False]

    # --- Chat history persistence (auto-save) ---
    chat_history_dir = get_chat_history_dir()
    chat_history_dir.mkdir(parents=True, exist_ok=True)
    session_created_at_ref: list[str] = [_now_ts()]
    chat_path_ref: list[Path | None] = [None]
    session_id_ref: list[str] = [_new_id()]

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
        path = chat_path_ref[0]
        if path is None:
            return
        payload = {
            "schema_version": CHAT_HISTORY_SCHEMA_VERSION,
            "session_id": session_id_ref[0],
            "created_at": session_created_at_ref[0],
            "assistant_selected": assistant_dd.value,
            "ollama": {"host": get_ollama_host(), "model": get_ollama_model()},
            "chat_history_dir": str(chat_history_dir),
            "messages": list(history),
        }
        try:
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _ensure_chat_file() -> None:
        """Create a temporary chat file name on first write."""
        if chat_path_ref[0] is not None:
            return
        ts = datetime.now().strftime("%y-%m-%d-%H%M%S")
        tmp = _unique_path(chat_history_dir, f"chat_{ts}")
        chat_path_ref[0] = tmp
        _set_chat_title_from_path(tmp)
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
                system = (
                    "You generate concise filenames for chat logs. "
                    "Return ONLY a short snake_case name (no spaces), WITHOUT extension. "
                    "Use 3-8 words max. Example: workflow_roundtrip_execution"
                )
                messages = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"User's first message:\n{first_message}"},
                ]

                def _call() -> str:
                    return ollama_integration.chat(
                        host=host,
                        model=model,
                        messages=messages,
                        timeout_s=OLLAMA_TIMEOUT_S,
                        options={"temperature": 0.2, "num_predict": 64},
                    )

                resp = await asyncio.to_thread(_call)
                base = _slugify_filename(resp)
            except Exception:
                base = _slugify_filename(first_message)

            try:
                old = chat_path_ref[0]
                if old is None:
                    return
                new_path = _unique_path(chat_history_dir, base)
                if new_path != old:
                    old.rename(new_path)
                    chat_path_ref[0] = new_path
                    _set_chat_title_from_path(new_path)
                    _persist_history()
            except OSError:
                pass

        page.run_task(_run)

    def _append(role: str, content: str, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        _ensure_chat_file()
        msg: dict[str, Any] = {
            "id": _new_id(),
            "ts": _now_ts(),
            "role": role,
            "content": content,
        }
        if meta:
            msg.update(meta)
        history.append(msg)
        is_user = role == "user"
        row_align = ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START
        text_color = ft.Colors.WHITE if is_user else ft.Colors.GREY_200

        # Wrap within available column width (no horizontal overflow).
        bubble = ft.Container(
            content=ft.Text(
                content,
                color=text_color,
                size=12,  # smaller, closer to editor text
                selectable=True,
                no_wrap=False,
                width=420,  # fixed max bubble width (older Flet has no Container.constraints)
            ),
            padding=ft.padding.symmetric(horizontal=10, vertical=6),
            border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.WHITE) if is_user else ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            width=420,
        )

        def _save_feedback(value: str) -> None:
            msg["feedback"] = {"type": "thumb", "value": value, "ts": _now_ts()}
            _persist_history()
            async def _toast_feedback() -> None:
                await _toast(page, "Feedback saved")

            page.run_task(_toast_feedback)

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
                width=420,
                padding=ft.padding.only(left=2, right=2, top=0, bottom=0),
            )
        # Align bubble without relying on ft.alignment center_right/left (not available in all Flet versions).
        row_children: list[ft.Control]
        if is_user:
            row_children = [ft.Container(expand=True), bubble]
        else:
            content_stack: ft.Control = bubble if feedback_bar is None else ft.Column([bubble, feedback_bar], spacing=0)
            row_children = [content_stack, ft.Container(expand=True)]
        messages_col.controls.append(
            ft.Row(
                row_children,
                alignment=row_align,
            )
        )
        messages_col.update()
        page.update()
        _persist_history()
        return msg

    def _set_busy(v: bool) -> None:
        busy[0] = v
        input_tf_first.disabled = v
        input_tf.disabled = v
        input_tf_first.update()
        input_tf.update()
        page.update()

    # Toggle input placement: top (first message) -> bottom (subsequent)
    top_input_container = ft.Container(content=input_tf_first, visible=True)
    bottom_input_row = ft.Row([input_tf], spacing=8, visible=False)

    def _after_first_send() -> None:
        if has_sent_any[0]:
            return
        has_sent_any[0] = True
        top_input_container.visible = False
        bottom_input_row.visible = True
        top_input_container.update()
        bottom_input_row.update()
        page.update()

    def _send_from_field(field: ft.TextField) -> None:
        text = (field.value or "").strip()
        if not text or busy[0]:
            return
        field.value = ""
        field.update()
        turn_id = _new_id()
        if not has_sent_any[0]:
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
                    msgs.extend(_messages_from_history(history))
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
                msgs.extend(_messages_from_history(history))
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
        history.clear()
        busy[0] = False
        has_sent_any[0] = False
        chat_path_ref[0] = None
        session_id_ref[0] = _new_id()
        session_created_at_ref[0] = _now_ts()

        # Reset inputs
        input_tf_first.value = ""
        input_tf.value = ""
        input_tf_first.disabled = False
        input_tf.disabled = False

        # Reset layout (top composer visible again)
        top_input_container.visible = True
        bottom_input_row.visible = False

        # Reset title
        _set_chat_title("new_chat")

        # Reset messages column (keep title at top)
        messages_col.controls = [chat_title_txt]

        # Best-effort refresh
        try:
            messages_col.update()
            top_input_container.update()
            bottom_input_row.update()
            input_tf_first.update()
            input_tf.update()
            page.update()
        except Exception:
            pass

    def _start_new_chat(_e: ft.ControlEvent) -> None:
        if busy[0]:
            return
        _reset_chat_ui()

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
            ft.Container(content=messages_col, expand=True),
            bottom_input_row,
        ],
        expand=True,
        spacing=8,
    )

