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
from typing import Any, Callable, Literal

import flet as ft

from assistants.process_assistant import process_assistant_apply
from assistants.prompts import RL_COACH_SYSTEM, WORKFLOW_DESIGNER_SYSTEM
from schemas.process_graph import ProcessGraph

from LLM_integrations import ollama as ollama_integration
from gui.flet.components.settings import get_ollama_host, get_ollama_model
from gui.flet.tools.notifications import show_toast


AssistantType = Literal["Workflow Designer", "RL Coach"]

# Model options
OLLAMA_NUM_PREDICT = 1024
OLLAMA_TIMEOUT_S = 300


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
        width=200,
        options=[
            ft.dropdown.Option("Workflow Designer"),
            ft.dropdown.Option("RL Coach"),
        ],
    )

    messages_col = ft.Column(
        [ft.Text("Talk to Workflow Designer (graph edits) or RL Coach (training).", size=12, color=ft.Colors.GREY_500)],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=8,
    )

    input_tf = ft.TextField(
        hint_text="Message...",
        multiline=False,
        min_lines=1,
        max_lines=1,
        expand=True,
    )
    send_btn = ft.IconButton(icon=ft.Icons.SEND)

    history: list[dict[str, Any]] = []  # {role, content}
    busy: list[bool] = [False]

    def _append(role: str, content: str) -> None:
        history.append({"role": role, "content": content})
        align = ft.MainAxisAlignment.END if role == "user" else ft.MainAxisAlignment.START
        color = ft.Colors.WHITE if role == "user" else ft.Colors.GREY_200
        messages_col.controls.append(
            ft.Row([ft.Text(content, color=color, size=13, selectable=True)], alignment=align)
        )
        messages_col.update()
        page.update()

    def _set_busy(v: bool) -> None:
        busy[0] = v
        input_tf.disabled = v
        send_btn.disabled = v
        input_tf.update()
        send_btn.update()
        page.update()

    def _send_from_ui() -> None:
        text = (input_tf.value or "").strip()
        if not text or busy[0]:
            return
        input_tf.value = ""
        input_tf.update()
        _append("user", text)
        _set_busy(True)

        async def _run() -> None:
            try:
                asst: AssistantType = (assistant_dd.value or "Workflow Designer")  # type: ignore[assignment]
                host = get_ollama_host()
                model = get_ollama_model()

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
                            options={"temperature": 0.3, "num_predict": OLLAMA_NUM_PREDICT},
                        )

                    content = await asyncio.to_thread(_call)
                    if not content:
                        content = "(No response from model.)"
                    edit = _parse_json_block(content)

                    # Apply edit if present and actionable
                    if isinstance(edit, dict) and edit.get("action") not in (None, "no_edit"):
                        try:
                            new_graph = process_assistant_apply(graph_ref[0] or {"units": [], "connections": []}, edit)
                            set_graph(new_graph)
                            await _toast(page, "Applied to graph")
                        except Exception as ex:
                            await _toast(page, f"Could not apply edit: {str(ex)[:120]}")

                    _append("assistant", content)
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
                        options={"temperature": 0.3, "num_predict": OLLAMA_NUM_PREDICT},
                    )

                content = await asyncio.to_thread(_call2)
                _append("assistant", content or "(No response from model.)")
                await _toast(page, "RL Coach reply (not applied in Flet yet)")
            except ImportError as ex:
                _append("assistant", str(ex))
            except Exception as ex:
                # Try to present nicer Ollama errors
                _append("assistant", ollama_integration.format_ollama_exception(ex))
            finally:
                _set_busy(False)

        page.run_task(_run)

    input_tf.on_submit = lambda _e: _send_from_ui()
    send_btn.on_click = lambda _e: _send_from_ui()

    return ft.Column(
        [
            ft.Row(
                [
                    ft.Icon(ft.Icons.SMART_TOY, size=30, color=ft.Colors.GREY_200),
                    ft.Container(expand=True),
                    assistant_dd,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Container(content=messages_col, expand=True),
            ft.Row(
                [
                    input_tf,
                    send_btn,
                ],
                spacing=8,
            ),
        ],
        expand=True,
        spacing=8,
    )

