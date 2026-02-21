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


def build_workflow_designer_system_prompt(
    graph_summary_dict: dict[str, Any],
    last_apply_result: dict[str, Any] | None,
    *,
    base_prompt: str,
    self_correction_template: str,
) -> str:
    """Build the full system prompt for Workflow Designer, including graph context and last apply result."""
    ctx = json.dumps(graph_summary_dict, indent=2)
    parts = [
        base_prompt,
        "\n\nCurrent process graph (summary):",
        ctx,
    ]
    if last_apply_result is not None:
        parts.append("\n\nLast apply result:")
        parts.append(
            json.dumps(
                {
                    "attempted": last_apply_result.get("attempted"),
                    "success": last_apply_result.get("success"),
                    "error": last_apply_result.get("error"),
                },
                indent=2,
            )
        )
        if last_apply_result.get("success") is False:
            error_msg = last_apply_result.get("error") or "Unknown error"
            parts.append(self_correction_template.format(error=error_msg))
    return "\n".join(parts)


def build_workflow_designer_messages(
    system_content: str,
    history: list[dict[str, Any]],
    user_message: str,
    messages_from_history: Callable[..., list[dict[str, str]]],
    *,
    max_turn_pairs: int = 3,
) -> list[dict[str, str]]:
    """Build LLM messages: system + trimmed history + user."""
    msgs: list[dict[str, str]] = [{"role": "system", "content": system_content}]
    msgs.extend(messages_from_history(history, max_turn_pairs=max_turn_pairs))
    msgs.append({"role": "user", "content": user_message})
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
    wf_result = apply_workflow_edits(current_graph, edits)

    if wf_result["success"]:
        apply_result["success"] = True
        current_for_summary = wf_result["graph"]
    else:
        apply_result["success"] = False
        apply_result["error"] = wf_result["error"]
        current_for_summary = current_graph

    last_apply_result = {
        "attempted": apply_result["attempted"],
        "success": apply_result["success"],
        "error": apply_result["error"],
        "graph_after": graph_summary(current_for_summary),
    }

    return {
        "kind": "applied" if wf_result["success"] else "apply_failed",
        "apply_result": apply_result,
        "edits": edits,
        "graph": wf_result["graph"] if wf_result["success"] else None,
        "last_apply_result": last_apply_result,
        "content_for_display": content.strip() or "(No explanation provided.)",
    }
