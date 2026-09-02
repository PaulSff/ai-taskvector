"""
Helpers to turn chat history and user input into model-facing context.

Used by agents chat to inject previous turn.
"""

from __future__ import annotations

from typing import cast

from agents.chat.session.state import AgentChatHistory
from core.schemas.primitives import Data, JsonValue, is_json_object_keyed_dict
from llm_integrations.client import LLMMessages

_NO_MESSAGE = "(No message provided.)"


def normalize_user_message_for_workflow(raw: object) -> str:
    """Ensure the user message is a proper string for the workflow."""
    if raw is None:
        return _NO_MESSAGE

    message = raw if isinstance(raw, str) else str(raw)
    message = message.replace("\x00", "").strip()

    return message or _NO_MESSAGE


def summarize_parsed_edits_for_context(
    edits: JsonValue,
    *,
    max_items: int = 28,
    max_len: int = 1800,
) -> str:
    """
    Compact description of graph edit actions for LLM context.
    """
    if not isinstance(edits, list) or not edits:
        return ""

    parts: list[str] = []

    for edit in edits[:max_items]:
        if not is_json_object_keyed_dict(edit):
            continue

        action_raw = edit.get("action")
        action = action_raw.strip() if isinstance(action_raw, str) else ""

        if action == "add_unit":
            unit_raw = edit.get("unit")
            unit = (
                unit_raw
                if is_json_object_keyed_dict(unit_raw)
                else {}
            )
            parts.append(
                f"add_unit {unit.get('id', '?')} ({unit.get('type', '?')})"
            )

        elif action == "remove_unit":
            parts.append(f"remove_unit {edit.get('unit_id', '?')}")

        elif action == "connect":
            parts.append(
                f"connect {edit.get('from', '?')} -> {edit.get('to', '?')}"
            )

        elif action == "disconnect":
            parts.append(
                f"disconnect {edit.get('from', '?')} - {edit.get('to', '?')}"
            )

        elif action == "set_params":
            parts.append(f"set_params {edit.get('id', '?')}")

        elif action == "replace_unit":
            find_unit_raw = edit.get("find_unit")
            find_unit = (
                find_unit_raw
                if is_json_object_keyed_dict(find_unit_raw)
                else {}
            )
            parts.append(f"replace_unit {find_unit.get('id', '?')}")

        elif action == "replace_graph":
            parts.append("replace_graph (full graph)")

        elif action == "import_workflow":
            parts.append(f"import_workflow {edit.get('source', '?')}")

        elif action in {
            "search",
            "web_search",
            "browse",
            "read_file",
            "grep",
            "formulas_calc",
            "delegate_request",
            "report",
            "read_code_block",
            "read_current_workflow",
            "add_todo_list",
            "remove_todo_list",
            "add_task",
            "remove_task",
            "mark_completed",
            "add_comment",
            "no_edit",
        } or action:
            parts.append(action)

    if not parts:
        return ""

    output = "; ".join(parts)

    if len(edits) > max_items:
        output += f"; … (+{len(edits) - max_items} more)"

    if len(output) > max_len:
        output = output[: max_len - 3] + "..."

    return output


async def messages_from_history(
    history: AgentChatHistory,
    *,
    max_turn_pairs: int = 10,
) -> LLMMessages:
    """Convert local history to LLM messages (role/content)."""
    from services.workflows.core_workflows.run_inline import (
        run_clean_text_for_chat_inline,
    )

    out: LLMMessages = []

    cap = max_turn_pairs * 2
    msgs = history[-cap:] if len(history) > cap else history

    for m in msgs:
        role = m.get("role")
        if role not in ("user", "agent"):
            continue

        raw_content = m.get("content")
        if not isinstance(raw_content, str):
            continue

        content = await run_clean_text_for_chat_inline(raw_content)
        if not content:
            if role == "agent":
                content = "(Previous response contained graph edits that were applied.)"
            else:
                continue

        out.append({"role": role, "content": content})

    return out


async def format_previous_turn(history: AgentChatHistory) -> str:
    """
    Format the last complete turn (last user + last agent) for the workflow.
    Includes any follow_up_context (RAG, web search, etc.) stored in the agent message meta
    so the model sees that context on the next turn.
    Returns "" if there is no complete previous turn.
    """
    from services.workflows.core_workflows.run_inline import (
        run_clean_text_for_chat_inline,
    )

    if not history or len(history) < 2:
        return ""

    last_agent: Data| None = None
    last_user_before: Data | None = None

    for message in reversed(history):
        role_raw = message.get("role")
        role = role_raw.strip().lower() if isinstance(role_raw, str) else ""

        if role == "agent" and last_agent is None:
            last_agent = message
        elif (
            role == "user"
            and last_agent is not None
            and last_user_before is None
        ):
            last_user_before = message
            break

    if last_user_before is None or last_agent is None:
        return ""

    user_content = (
        last_user_before.get("content")
        or last_user_before.get("content_for_display")
        or ""
    )
    if not isinstance(user_content, str):
        user_content = str(user_content or "")

    user_content = (
        await run_clean_text_for_chat_inline(user_content)
    ).strip() or "(no message)"

    asst_content = (
        last_agent.get("content") or last_agent.get("content_for_display") or ""
    )
    if not isinstance(asst_content, str):
        asst_content = str(asst_content or "")

    asst_stripped = (await run_clean_text_for_chat_inline(asst_content)).strip()

    if not asst_stripped or asst_stripped.lower() == "(no response)":
        edit_summary = summarize_parsed_edits_for_context(
            cast(JsonValue, last_agent.get("parsed_edits"))
        )

        if edit_summary:
            asst_content = (
                "[Previous agent message was mostly JSON edit blocks.] "
                f"Summary of actions: {edit_summary}"
            )
        else:
            asst_content = (
                asst_stripped
                or "(Previous response had no plain text outside JSON blocks; no parsed_edits stored.)"
            )
    else:
        asst_content = asst_stripped


    meta_raw = last_agent.get("meta")
    meta = (
        cast(dict[str, object], meta_raw)
        if isinstance(meta_raw, dict)
        else {}
    )

    follow_ups_raw = last_agent.get("follow_up_contexts") or meta.get(
        "follow_up_contexts"
    )

    if isinstance(follow_ups_raw, list) and follow_ups_raw:
        follow_ups = cast(list[object], follow_ups_raw)

        context_block = "Context used in that turn:\n" + "\n\n".join(
            str(context).strip()
            for context in follow_ups
            if context
        )

        asst_content = context_block + "\n\n--- My response ---\n\n" + asst_content



    return f"User: {user_content}\n\nagent: {asst_content}"
