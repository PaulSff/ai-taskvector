"""
Helpers to turn chat history and user input into model-facing context (no Flet UI).

Used by assistants chat for inject_previous_turn, follow-up chains, and workflow user_message.
"""
from __future__ import annotations

from typing import Any

from gui.flet.components.workflow.core_workflows import run_clean_text_for_chat


def normalize_user_message_for_workflow(raw: Any) -> str:
    """Ensure the user message is a proper string for the workflow (inject_user_message.data)."""
    if raw is None:
        return "(No message provided.)"
    s = raw if isinstance(raw, str) else str(raw)
    s = s.replace("\x00", "").strip()
    return s if s else "(No message provided.)"


def summarize_parsed_edits_for_context(
    edits: Any,
    *,
    max_items: int = 28,
    max_len: int = 1800,
) -> str:
    """
    Compact description of graph edit actions for LLM context.
    Workflow Designer replies are often only ```json``` blocks; CleanText (via run_clean_text_for_chat)
    then removes most of it, so the model would otherwise see '(no response)' for the previous turn.
    """
    if not isinstance(edits, list) or not edits:
        return ""
    parts: list[str] = []
    for e in edits[:max_items]:
        if not isinstance(e, dict):
            continue
        act = (e.get("action") or "").strip()
        if act == "add_unit":
            u = e.get("unit") if isinstance(e.get("unit"), dict) else {}
            parts.append(f"add_unit {u.get('id', '?')} ({u.get('type', '?')})")
        elif act == "remove_unit":
            parts.append(f"remove_unit {e.get('unit_id', '?')}")
        elif act == "connect":
            parts.append(f"connect {e.get('from', '?')} -> {e.get('to', '?')}")
        elif act == "disconnect":
            parts.append(f"disconnect {e.get('from', '?')} - {e.get('to', '?')}")
        elif act == "set_params":
            parts.append(f"set_params {e.get('id', '?')}")
        elif act == "replace_unit":
            fu = e.get("find_unit") if isinstance(e.get("find_unit"), dict) else {}
            parts.append(f"replace_unit {fu.get('id', '?')}")
        elif act == "replace_graph":
            parts.append("replace_graph (full graph)")
        elif act == "import_workflow":
            parts.append(f"import_workflow {e.get('source', '?')}")
        elif act in ("search", "web_search", "browse", "read_file", "grep", "report", "read_code_block"):
            parts.append(f"{act}")
        elif act in (
            "add_todo_list",
            "remove_todo_list",
            "add_task",
            "remove_task",
            "mark_completed",
            "add_comment",
            "no_edit",
        ):
            parts.append(f"{act}")
        elif act:
            parts.append(act)
    if not parts:
        return ""
    out = "; ".join(parts)
    if len(edits) > max_items:
        out += f"; … (+{len(edits) - max_items} more)"
    if len(out) > max_len:
        out = out[: max_len - 3] + "..."
    return out


def messages_from_history(
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

        content = run_clean_text_for_chat(raw_content)
        if not content:
            if role == "assistant":
                content = "(Previous response contained graph edits that were applied.)"
            else:
                continue

        out.append({"role": role, "content": content})

    return out


def format_previous_turn(history: list[dict[str, Any]]) -> str:
    """
    Format the last complete turn (last user + last assistant) for the workflow.
    Includes any follow_up_context (RAG, web search, etc.) stored in the assistant message meta
    so the model sees that context on the next turn.
    Returns "" if there is no complete previous turn.
    """
    if not history or len(history) < 2:
        return ""
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
    user_content = run_clean_text_for_chat(user_content).strip() or "(no message)"
    asst_content = (last_assistant.get("content") or last_assistant.get("content_for_display") or "")
    if not isinstance(asst_content, str):
        asst_content = str(asst_content or "")
    asst_stripped = run_clean_text_for_chat(asst_content).strip()
    if not asst_stripped or asst_stripped.lower() == "(no response)":
        edit_summary = summarize_parsed_edits_for_context(last_assistant.get("parsed_edits"))
        if edit_summary:
            asst_content = (
                "[Previous assistant message was mostly JSON edit blocks.] "
                f"Summary of actions: {edit_summary}"
            )
        else:
            asst_content = (
                asst_stripped
                or "(Previous response had no plain text outside JSON blocks; no parsed_edits stored.)"
            )
    else:
        asst_content = asst_stripped
    follow_ups = last_assistant.get("follow_up_contexts") or (last_assistant.get("meta") or {}).get("follow_up_contexts")
    if isinstance(follow_ups, list) and follow_ups:
        context_block = "Context used in that turn:\n" + "\n\n".join(str(c).strip() for c in follow_ups if c)
        asst_content = context_block + "\n\n--- My response ---\n\n" + asst_content
    return f"User: {user_content}\n\nAssistant: {asst_content}"
