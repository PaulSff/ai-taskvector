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
    WORKFLOW_DESIGNER_ADD_CODE_BLOCK_LINE,
    WORKFLOW_DESIGNER_ADD_ENVIRONMENT_LINE,
    WORKFLOW_DESIGNER_AI_TRAINING_EXTERNAL,
    WORKFLOW_DESIGNER_AI_TRAINING_NATIVE,
    WORKFLOW_DESIGNER_DO_NOT_REPEAT,
    WORKFLOW_DESIGNER_RECENT_CHANGES_PREFIX,
    WORKFLOW_DESIGNER_TURN_STATE_PREFIX,
)
from units.units_library import format_units_library_for_prompt
from core.normalizer.runtime_detector import is_external_runtime, runtime_label

try:
    from gui.flet.components.settings import (
        DEFAULT_CODING_IS_ALLOWED,
        KEY_CODING_IS_ALLOWED,
        load_settings,
    )
except ImportError:
    load_settings = None
    KEY_CODING_IS_ALLOWED = "coding_is_allowed"
    DEFAULT_CODING_IS_ALLOWED = False


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
    rag_context: str | None = None,
) -> str:
    """Build the full system prompt for Workflow Designer, including graph context and optional RAG."""
    # Inject runtime and AI training block from graph summary (centralized in normalizer.runtime_detector).
    runtime = runtime_label(graph_summary_dict)
    base_prompt = base_prompt.replace("{runtime}", runtime)
    ai_training_block = (
        WORKFLOW_DESIGNER_AI_TRAINING_EXTERNAL
        if is_external_runtime(graph_summary_dict)
        else WORKFLOW_DESIGNER_AI_TRAINING_NATIVE
    )
    base_prompt = base_prompt.replace("{ai_training_integration}", ai_training_block)
    # add_environment is native-only; external runtime has no env-specific units
    add_environment_block = (
        WORKFLOW_DESIGNER_ADD_ENVIRONMENT_LINE
        if not is_external_runtime(graph_summary_dict)
        else ""
    )
    base_prompt = base_prompt.replace("{add_environment_edit}", add_environment_block)

    coding_is_allowed = (
        bool(load_settings().get(KEY_CODING_IS_ALLOWED, DEFAULT_CODING_IS_ALLOWED))
        if load_settings is not None
        else DEFAULT_CODING_IS_ALLOWED
    )
    add_code_block_block = WORKFLOW_DESIGNER_ADD_CODE_BLOCK_LINE if coding_is_allowed else ""
    base_prompt = base_prompt.replace("{add_code_block_edit}", add_code_block_block)

    ctx = json.dumps(graph_summary_dict, indent=2)

    # State line at top so the model knows what happened last turn
    if last_apply_result is None:
        state_line = WORKFLOW_DESIGNER_TURN_STATE_PREFIX + "Last action: none."
    elif last_apply_result.get("success") is False:
        err = last_apply_result.get("error") or "Unknown error"
        state_line = WORKFLOW_DESIGNER_TURN_STATE_PREFIX + f"Last action: failed (error: {err})."
    else:
        summary = last_apply_result.get("edits_summary") or ""
        if summary:
            state_line = WORKFLOW_DESIGNER_TURN_STATE_PREFIX + f"Last action: applied successfully ({summary})."
        else:
            state_line = WORKFLOW_DESIGNER_TURN_STATE_PREFIX + "Last action: applied successfully."

    parts = [base_prompt, "\n\n" + state_line]

    if recent_changes:
        parts.append("\n\n" + WORKFLOW_DESIGNER_RECENT_CHANGES_PREFIX + recent_changes)
        parts.append("\n" + WORKFLOW_DESIGNER_DO_NOT_REPEAT)

    parts.append("\n\nCurrent process graph (summary):")
    parts.append(ctx)

    units_library = format_units_library_for_prompt(graph_summary_dict)
    if units_library.strip():
        parts.append("\n\n" + units_library.strip())

    if rag_context and rag_context.strip():
        parts.append("\n\n" + rag_context.strip())

    if last_apply_result is not None:
        if last_apply_result.get("success") is False:
            error_msg = last_apply_result.get("error") or "Unknown error"
            parts.append("\n\nLast edit failed. " + self_correction_template.format(error=error_msg))
        else:
            summary = last_apply_result.get("edits_summary") or ""
            if summary:
                parts.append("\n\nLast edit applied successfully. Applied: " + summary)
            else:
                parts.append("\n\nLast edit applied successfully.")
            parts.append("\n" + WORKFLOW_DESIGNER_DO_NOT_REPEAT)

    return "\n".join(parts)


def build_workflow_designer_messages(
    system_content: str,
    history: list[dict[str, Any]],
    user_message: str,
    messages_from_history: Callable[..., list[dict[str, str]]],
    *,
    max_turn_pairs: int = 2,
) -> list[dict[str, str]]:
    """Build LLM messages: system (already includes RAG when provided) + trimmed history + user."""
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

    rag_search_results = ""
    read_code_block_results = ""
    if isinstance(parse_result, dict) and parse_result.get("rag_search"):
        try:
            from gui.flet.chat_with_the_assistants.rag_context import get_rag_context
            top_k = parse_result.get("rag_search_max_results")
            rag_search_results = get_rag_context(
                parse_result["rag_search"], "Workflow Designer", top_k=top_k
            ) or ""
        except Exception:
            pass

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
            "requested_unit_specs": [],
            "request_file_content": [],
            "rag_search_results": rag_search_results,
            "read_code_block_results": read_code_block_results,
        }

    requested_unit_specs: list[str] = []
    request_file_content: list[str] = []
    if isinstance(parse_result, dict) and "edits" in parse_result:
        edits = parse_result["edits"]
        requested_unit_specs = parse_result.get("request_unit_specs") or []
        request_file_content = parse_result.get("request_file_content") or []
    else:
        edits = parse_result

    apply_result: dict[str, Any] = {"attempted": False, "success": None, "error": None}

    if not edits:
        # read_code_block with no edits: still resolve from current graph
        if isinstance(parse_result, dict) and parse_result.get("read_code_block_ids"):
            _graph = current_graph
            if hasattr(_graph, "model_dump"):
                _graph = _graph.model_dump(by_alias=True)
            blocks = (_graph or {}).get("code_blocks") or []
            block_by_id = {str(b.get("id")): b for b in blocks if isinstance(b, dict) and b.get("id")}
            parts = []
            for bid in parse_result["read_code_block_ids"]:
                b = block_by_id.get(str(bid).strip())
                if b:
                    lang = b.get("language", "?")
                    src = b.get("source") or ""
                    parts.append(f"Code block for unit {bid} ({lang}):\n\n{src}\n")
            if parts:
                read_code_block_results = "\n".join(parts)
        return {
            "kind": "no_edits",
            "apply_result": apply_result,
            "edits": [],
            "graph": current_graph,
            "last_apply_result": None,
            "content_for_display": content.strip() or "(No explanation provided.)",
            "requested_unit_specs": requested_unit_specs,
            "request_file_content": request_file_content,
            "rag_search_results": rag_search_results,
            "read_code_block_results": read_code_block_results,
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

    # Resolve read_code_block: get requested code block source from the graph (after apply)
    if isinstance(parse_result, dict) and parse_result.get("read_code_block_ids"):
        _graph = wf_result["graph"] if wf_result["success"] else current_graph
        if _graph is not None:
            if hasattr(_graph, "model_dump"):
                _graph = _graph.model_dump(by_alias=True)
            blocks = (_graph or {}).get("code_blocks") or []
            block_by_id = {str(b.get("id")): b for b in blocks if isinstance(b, dict) and b.get("id")}
            parts = []
            for bid in parse_result["read_code_block_ids"]:
                b = block_by_id.get(str(bid).strip())
                if b:
                    lang = b.get("language", "?")
                    src = b.get("source") or ""
                    parts.append(f"Code block for unit {bid} ({lang}):\n\n{src}\n")
            if parts:
                read_code_block_results = "\n".join(parts)

    return {
        "kind": "applied" if wf_result["success"] else "apply_failed",
        "apply_result": apply_result,
        "edits": edits,
        "graph": wf_result["graph"] if wf_result["success"] else None,
        "last_apply_result": last_apply_result,
        "content_for_display": content.strip() or "(No explanation provided.)",
        "requested_unit_specs": requested_unit_specs,
        "request_file_content": request_file_content,
        "rag_search_results": rag_search_results,
        "read_code_block_results": read_code_block_results,
    }
