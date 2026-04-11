"""
Canonical Workflow Designer follow-up tools: tool id + parser_output key.

Order matches ``workflow_designer_followups.run_parser_output_follow_up_chain`` (must stay in sync).
"""
from __future__ import annotations

# (tool_id, key on normalized parser_output dict from normalize_follow_up_parser_output)
ORDERED_WORKFLOW_DESIGNER_TOOLS: tuple[tuple[str, str], ...] = (
    ("read_code_block", "read_code_block_ids"),
    ("run_workflow", "run_workflow"),
    ("grep", "grep"),
    ("read_file", "read_file"),
    ("rag_search", "rag_search"),
    ("web_search", "web_search"),
    ("browse", "browse_url"),
    ("github", "github"),
    ("report", "report"),
    ("add_comment", "add_comment"),
    ("todo_manager", "todo_manager"),
)


def workflow_designer_tool_ids() -> tuple[str, ...]:
    """Ordered tool ids for role.yaml ``tools`` and future generic runner."""
    return tuple(tid for tid, _ in ORDERED_WORKFLOW_DESIGNER_TOOLS)


def parser_key_for_tool(tool_id: str) -> str | None:
    """Return ``parser_output`` dict key for a tool id, or None if unknown."""
    for tid, pkey in ORDERED_WORKFLOW_DESIGNER_TOOLS:
        if tid == tool_id:
            return pkey
    return None


def tool_id_for_parser_key(parser_key: str) -> str | None:
    """Inverse map for introspection."""
    for tid, pkey in ORDERED_WORKFLOW_DESIGNER_TOOLS:
        if pkey == parser_key:
            return tid
    return None
