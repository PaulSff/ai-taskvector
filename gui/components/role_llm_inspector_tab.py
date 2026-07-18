from __future__ import annotations

from typing import Any
import flet as ft


def build_role_llm_inspector_tab(
    page: ft.Page, chat_panel_api: dict[str, Any]
) -> ft.Control:
    hint = ft.Text(
        "After each agents-chat workflow run (any role), the system prompt and user message "
        "last sent to LLMAgent appear below (from the graph’s Prompt unit, e.g. prompt_llm).",
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
        # Expect two wrapper cases:
        # - in_progress/final under resp["message"]
        # - in_progress/final under resp["outputs"]["orchestrator"]["message"]
        wrapper = None

        outer_msg = resp.get("message")
        if isinstance(outer_msg, dict) and outer_msg.get("type") in ("in_progress", "final"):
            wrapper = outer_msg

        if wrapper is None:
            outputs = resp.get("outputs")
            if isinstance(outputs, dict):
                out_orch = outputs.get("orchestrator")
                if isinstance(out_orch, dict):
                    out_msg = out_orch.get("message")
                    if isinstance(out_msg, dict) and out_msg.get("type") in (
                        "in_progress",
                        "final",
                    ):
                        wrapper = out_orch

        if not isinstance(wrapper, dict):
            return

        orch = wrapper.get("orchestrator")
        msg = orch.get("message") if isinstance(orch, dict) else None
        llm_user_message = msg.get("llm_user_message") if isinstance(msg, dict) else None

        if not isinstance(llm_user_message, dict):
            return

        sp = llm_user_message.get("llm_system_prompt")
        um = llm_user_message.get("llm_user_message")

        if isinstance(sp, str):
            system_tf.value = sp
        if isinstance(um, str):
            user_tf.value = um

        status.value = "Last update: after a role chat workflow run (in_progress/final)."
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
