"""
Workflow Designer assistant handler: system prompt, message building, and response handling.

Orchestrates graph edits: parse LLM output, apply edits, return structured result for the chat UI.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from assistants.process_assistant import (
    apply_workflow_edits,
    graph_summary,
    parse_workflow_edits,
)
from assistants.prompts import (
    WORKFLOW_DESIGNER_DO_NOT_REPEAT,
    WORKFLOW_DESIGNER_RECENT_CHANGES_PREFIX,
)


def _edits_summary(edits: list[dict[str, Any]]) -> str:
    """Produce a short, readable summary of edits for LLM context."""
    parts: list[str] = []
    for e in edits:
        if not isinstance(e, dict):
            continue
        action = e.get("action") or "unknown"
        if action == "no_edit":
            continue
        if action == "import_unit":
            parts.append(f"import_unit {e.get('node_id', '?')}")
        elif action == "import_workflow":
            parts.append(f"import_workflow {e.get('source', '?')}")
        elif action == "add_unit":
            u = e.get("unit") or {}
            uid = u.get("id", "?")
            typ = u.get("type", "")
            parts.append(f"add_unit {uid} ({typ})")
        elif action == "remove_unit":
            parts.append(f"remove_unit {e.get('unit_id', '?')}")
        elif action == "connect":
            parts.append(f"connect {e.get('from', '?')} -> {e.get('to', '?')}")
        elif action == "disconnect":
            parts.append(f"disconnect {e.get('from', '?')} -> {e.get('to', '?')}")
        elif action == "replace_unit":
            find_id = (e.get("find_unit") or {}).get("id", "?")
            rep = e.get("replace_with") or {}
            rep_id = rep.get("id", "?")
            parts.append(f"replace_unit {find_id} -> {rep_id}")
        else:
            parts.append(action)
    return "; ".join(parts) if parts else ""


def build_workflow_designer_system_prompt(
    graph_summary_dict: dict[str, Any],
    last_apply_result: dict[str, Any] | None,
    *,
    base_prompt: str,
    self_correction_template: str,
    recent_changes: str | None = None,
) -> str:
    """Build the full system prompt for Workflow Designer, including graph context."""
    ctx = json.dumps(graph_summary_dict, indent=2)
    parts = [base_prompt]

    if recent_changes:
        parts.append("\n\n" + WORKFLOW_DESIGNER_RECENT_CHANGES_PREFIX + recent_changes)
        parts.append("\n" + WORKFLOW_DESIGNER_DO_NOT_REPEAT)

    parts.append("\n\nCurrent process graph (summary):")
    parts.append(ctx)

    if last_apply_result is not None and last_apply_result.get("success") is False:
        error_msg = last_apply_result.get("error") or "Unknown error"
        parts.append("\n\nLast edit failed. " + self_correction_template.format(error=error_msg))

    return "\n".join(parts)


def build_workflow_designer_messages(
    system_content: str,
    history: list[dict[str, Any]],
    user_message: str,
    messages_from_history: Callable[..., list[dict[str, str]]],
    *,
    max_turn_pairs: int = 3,
    rag_context: str | None = None,
) -> list[dict[str, str]]:
    """Build LLM messages: system + trimmed history + user (with optional RAG context)."""
    msgs: list[dict[str, str]] = [{"role": "system", "content": system_content}]
    msgs.extend(messages_from_history(history, max_turn_pairs=max_turn_pairs))
    user_content = user_message
    if rag_context:
        user_content = f"{rag_context}\n\nUser request: {user_message}"
    msgs.append({"role": "user", "content": user_content})
    return msgs


def handle_workflow_edits_response(
    content: str,
    current_graph: Any,
) -> dict[str, Any]:
    """
    Parse LLM content, apply edits if any, return structured result.

    Returns dict with:
        kind: "parse_error" | "applied" | "no_edits"
        apply_result: {attempted, success, error}
        edits: list of edit dicts
        graph: ProcessGraph | None (only when kind=="applied" and success)
        last_apply_result: dict to store for next turn (or None if no edits)
    """
    parse_result = parse_workflow_edits(content)

    if isinstance(parse_result, dict) and "parse_error" in parse_result:
        apply_result = {
            "attempted": True,
            "success": False,
            "error": parse_result["parse_error"],
        }
        return {
            "kind": "parse_error",
            "apply_result": apply_result,
            "edits": [],
            "graph": None,
            "last_apply_result": apply_result,
            "content_for_display": content.strip() or "(No explanation provided.)",
        }

    edits: list[dict[str, Any]] = parse_result
    apply_result: dict[str, Any] = {"attempted": False, "success": None, "error": None}

    if not edits:
        return {
            "kind": "no_edits",
            "apply_result": apply_result,
            "edits": [],
            "graph": None,
            "last_apply_result": None,
            "content_for_display": content.strip() or "(No explanation provided.)",
        }

    apply_result["attempted"] = True
    rag_index_dir = None
    rag_embedding_model = None
    try:
        from gui.flet.components.settings import get_rag_embedding_model, get_rag_index_dir

        rag_index_dir = str(get_rag_index_dir())
        rag_embedding_model = get_rag_embedding_model()
    except ImportError:
        pass
    wf_result = apply_workflow_edits(
        current_graph,
        edits,
        rag_index_dir=rag_index_dir,
        rag_embedding_model=rag_embedding_model,
    )

    if wf_result["success"]:
        apply_result["success"] = True
        current_for_summary = wf_result["graph"]
    else:
        apply_result["success"] = False
        apply_result["error"] = wf_result["error"]
        current_for_summary = current_graph

    last_apply_result: dict[str, Any] = {
        "attempted": apply_result["attempted"],
        "success": apply_result["success"],
        "error": apply_result["error"],
        "graph_after": graph_summary(current_for_summary),
    }
    if apply_result.get("success") is True:
        summary = _edits_summary(edits)
        if summary:
            last_apply_result["edits_summary"] = summary

    return {
        "kind": "applied" if wf_result["success"] else "apply_failed",
        "apply_result": apply_result,
        "edits": edits,
        "graph": wf_result["graph"] if wf_result["success"] else None,
        "last_apply_result": last_apply_result,
        "content_for_display": content.strip() or "(No explanation provided.)",
    }
