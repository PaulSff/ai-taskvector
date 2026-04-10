"""
Canonical Workflow Designer follow-up tools: skill id + parser_output key.

Order matches ``workflow_designer_followups.run_parser_output_follow_up_chain`` (must stay in sync).
"""
from __future__ import annotations

# (skill_id, key on normalized parser_output dict from normalize_follow_up_parser_output)
ORDERED_WORKFLOW_DESIGNER_SKILLS: tuple[tuple[str, str], ...] = (
    ("read_code_block", "read_code_block_ids"),
    ("run_workflow", "run_workflow"),
    ("grep", "grep"),
    ("read_file", "read_file"),
    ("rag_search", "rag_search"),
    ("web_search", "web_search"),
    ("browse", "browse_url"),
    ("github", "github"),
    ("report", "report"),
)


def workflow_designer_skill_ids() -> tuple[str, ...]:
    """Ordered skill ids for role.yaml ``skills`` and future generic runner."""
    return tuple(sid for sid, _ in ORDERED_WORKFLOW_DESIGNER_SKILLS)


def parser_key_for_skill(skill_id: str) -> str | None:
    """Return ``parser_output`` dict key for a skill id, or None if unknown."""
    for sid, pkey in ORDERED_WORKFLOW_DESIGNER_SKILLS:
        if sid == skill_id:
            return pkey
    return None


def skill_id_for_parser_key(parser_key: str) -> str | None:
    """Inverse map for introspection."""
    for sid, pkey in ORDERED_WORKFLOW_DESIGNER_SKILLS:
        if pkey == parser_key:
            return sid
    return None
