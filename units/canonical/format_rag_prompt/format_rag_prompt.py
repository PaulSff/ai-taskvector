"""
FormatRagPrompt unit: table of RAG results → formatted "Relevant context from knowledge base" block.

Input: table (list of {text, metadata, score}). Output: data (str) for Merge/Prompt.
All limits are taken from unit params (max_chars, snippet_max); see README.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit


def _format_table(table: list[Any], max_chars: int, snippet_max: int) -> str:
    """Format RAG result rows into the prompt block string."""
    if not table or not isinstance(table, list):
        return ""
    order = ("document", "workflow", "flow_library", "node", "other")
    typed: list[tuple[str, str]] = []
    total = 0
    for r in table:
        if not isinstance(r, dict):
            continue
        meta = r.get("metadata") or {}
        text = (r.get("text") or "").strip()
        if not text:
            continue
        ct = meta.get("content_type", "") or "other"
        source = meta.get("file_path") or meta.get("raw_json_path") or meta.get("source") or meta.get("id") or "?"
        label = meta.get("name") or source
        snippet = text.replace("\n", " ")[:snippet_max]
        # For workflow/flow_library, always show source (path) so the model can use it for import_workflow.
        if ct in ("workflow", "flow_library") and source and source != "?":
            entry = f"[{ct}] source: {source}\n  {label}: {snippet}"
        elif ct and ct != "other":
            entry = f"[{ct}] {label}: {snippet}"
        else:
            entry = f"{label}: {snippet}"
        if total + len(entry) + 2 > max_chars:
            break
        typed.append((ct, entry))
        total += len(entry) + 2
    if not typed:
        return ""
    section_sep = "\n\n--- "
    section_end = " ---\n\n"
    by_type: dict[str, list[str]] = {}
    for ct, entry in typed:
        key = ct if ct in order else "other"
        by_type.setdefault(key, []).append(entry)
    block_parts = ["Relevant context from knowledge base:"]
    section_labels = {"document": "Documents", "workflow": "Workflows", "flow_library": "Flow libraries", "node": "Nodes", "other": "Other"}
    for key in order:
        if key not in by_type:
            continue
        label = section_labels.get(key, key.replace("_", " ").capitalize() + "s")
        block_parts.append(section_sep + label + section_end + "\n\n".join(by_type[key]))
    block = "".join(block_parts)
    block += "\n\nFor import_workflow: use the path that appears after \"source:\" in each workflow/flow_library entry as the \"source\" value. Copy it as-is."
    return block


FORMAT_RAG_PROMPT_INPUT_PORTS = [("table", "Any")]
FORMAT_RAG_PROMPT_OUTPUT_PORTS = [("data", "str")]


def _format_rag_prompt_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Format RAG results table into prompt block string. Params from graph only: max_chars, snippet_max."""
    table = inputs.get("table")
    if not isinstance(table, list):
        table = []
    max_chars = params.get("max_chars")
    snippet_max = params.get("snippet_max")
    if max_chars is None or snippet_max is None:
        return ({"data": ""}, state)
    try:
        max_chars = int(max_chars)
        snippet_max = int(snippet_max)
    except (TypeError, ValueError):
        return ({"data": ""}, state)
    if max_chars < 1 or snippet_max < 1:
        return ({"data": ""}, state)
    data = _format_table(table, max_chars, snippet_max)
    return ({"data": data}, state)


def register_format_rag_prompt() -> None:
    """Register the FormatRagPrompt unit type."""
    register_unit(UnitSpec(
        type_name="FormatRagPrompt",
        input_ports=FORMAT_RAG_PROMPT_INPUT_PORTS,
        output_ports=FORMAT_RAG_PROMPT_OUTPUT_PORTS,
        step_fn=_format_rag_prompt_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Formats a table of RAG results (text, metadata, score) into the prompt block string. Params: max_chars, snippet_max.",
    ))


__all__ = ["register_format_rag_prompt", "FORMAT_RAG_PROMPT_INPUT_PORTS", "FORMAT_RAG_PROMPT_OUTPUT_PORTS"]
