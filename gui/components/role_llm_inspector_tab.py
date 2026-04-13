"""
Dev-only tab: last role chat LLM inputs (system_prompt + user_message from Prompt → LLMAgent).

Registers ``chat_panel_api["record_llm_prompt_view"]``. Any role handler should call
``record_llm_prompt_view_if_present`` after a workflow run whose runner attaches fields via
``attach_llm_prompt_debug_from_outputs``.
"""

from __future__ import annotations

from typing import Any

import flet as ft


def build_role_llm_inspector_tab(page: ft.Page, chat_panel_api: dict[str, Any]) -> ft.Control:
    hint = ft.Text(
        "After each assistants-chat workflow run (any role), the system prompt and user message "
        "last sent to LLMAgent appear below (from the graph’s Prompt unit, e.g. prompt_llm).",
        size=11,
        color=ft.Colors.GREY_500,
    )
    status = ft.Text("(No LLM call recorded yet in this session.)", size=11, color=ft.Colors.GREY_600)

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
        sp = resp.get("llm_system_prompt")
        um = resp.get("llm_user_message")
        if isinstance(sp, str):
            system_tf.value = sp
        if isinstance(um, str):
            user_tf.value = um
        status.value = "Last update: after a role chat workflow run (Workflow Designer, RL Coach, …)."
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
