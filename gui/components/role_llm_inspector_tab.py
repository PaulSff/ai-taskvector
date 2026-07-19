from __future__ import annotations

from typing import Any
import flet as ft


def build_role_llm_inspector_tab(
    page: ft.Page, chat_panel_api: dict[str, Any]
) -> ft.Control:
    hint = ft.Text(
        "Following Agent context. ",
        size=11,
        color=ft.Colors.GREY_500,
    )
    status = ft.Text(
        "(No LLM call recorded yet in this session.)", size=11, color=ft.Colors.GREY_600
    )

    def _field(label: str) -> ft.TextField:
        return ft.TextField(
            label=label,
            multiline=True,
            min_lines=6,
            max_lines=40,
            read_only=True,
            expand=True,
            text_style=ft.TextStyle(font_family="monospace", size=11),
        )

    system_tf = _field("system_prompt → LLMAgent")
    user_tf = _field("user_message → LLMAgent")

    def _record_llm_prompt_view(resp: dict[str, Any]) -> None:
        # Your current shape (from debug):
        # resp["orchestrator"]["message"] = {"type": ..., "message": {...}}
        out_orch = resp.get("orchestrator")
        if not isinstance(out_orch, dict):
            return

        out_msg = out_orch.get("message")
        if not isinstance(out_msg, dict):
            return

        # This is the dict that contains llm_system_prompt + llm_user_message
        inner = out_msg.get("message")
        if not isinstance(inner, dict):
            return

        sp = inner.get("llm_system_prompt")
        um = inner.get("llm_user_message")

        if not isinstance(sp, str) and not isinstance(um, str):
            return

        if isinstance(sp, str):
            system_tf.value = sp
        if isinstance(um, str):
            user_tf.value = um

        status.value = "Last turn:"
        status.color = ft.Colors.GREY_500
        try:
            system_tf.update()
            user_tf.update()
            status.update()
        except Exception:
            try:
                page.update()
            except Exception:
                pass

    chat_panel_api["record_llm_prompt_view"] = _record_llm_prompt_view

    return ft.Container(
        content=ft.Column(
            [
                hint,
                status,
                ft.Row([ft.Text("System", size=12, weight=ft.FontWeight.W_500)]),
                ft.Container(content=system_tf, expand=True),
                ft.Row([ft.Text("User", size=12, weight=ft.FontWeight.W_500)]),
                ft.Container(content=user_tf, expand=True),
            ],
            expand=True,
            spacing=8,
        ),
        padding=16,
        expand=True,
    )
