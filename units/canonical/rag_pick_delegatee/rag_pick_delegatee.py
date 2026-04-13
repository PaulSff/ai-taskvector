"""
RagPickDelegatee: from nested RAG workflow outputs, pick the first TeamMember row for auto-delegation.

Reads ``rag_filter.table`` (else ``rag_search.table``) from RunWorkflow's ``data`` payload. Chooses the
first row whose chunk is from ``assistants_team_members.md`` or whose text contains a ``## TeamMember:``
heading; extracts the role id after that heading.
"""
from __future__ import annotations

import re
from typing import Any

from units.registry import UnitSpec, register_unit

TEAM_MEMBERS_MARK = "assistants_team_members.md"
TEAM_HEADER_RE = re.compile(r"^##\s*TeamMember:\s*([^\s#\n]+)", re.MULTILINE)

RAG_PICK_DELEGATEE_INPUT_PORTS = [("nested", "Any"), ("user_message", "Any")]
RAG_PICK_DELEGATEE_OUTPUT_PORTS = [("data", "Any")]


def _normalize_user_message(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        v = raw.get("user_message")
        if v is None:
            return ""
        return str(v).strip()
    return ""


def _table_from_nested(nested: Any) -> list[Any]:
    if not isinstance(nested, dict):
        return []
    rf = nested.get("rag_filter")
    if isinstance(rf, dict):
        t = rf.get("table")
        if isinstance(t, list):
            return t
    rs = nested.get("rag_search")
    if isinstance(rs, dict):
        t = rs.get("table")
        if isinstance(t, list):
            return t
    return []


def _role_id_from_row(row: Any) -> str | None:
    if not isinstance(row, dict):
        return None
    text = str(row.get("text") or "")
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    fp = str(meta.get("file_path") or "").replace("\\", "/")
    team_doc = TEAM_MEMBERS_MARK in fp
    if not team_doc and "## TeamMember:" not in text and "##TeamMember:" not in text.replace(" ", ""):
        return None
    m = TEAM_HEADER_RE.search(text)
    if not m:
        return None
    rid = (m.group(1) or "").strip()
    return rid or None


def _rag_pick_delegatee_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    nested = inputs.get("nested")
    um = _normalize_user_message(inputs.get("user_message"))
    delegate_to = ""
    rows = _table_from_nested(nested)
    for row in rows:
        rid = _role_id_from_row(row)
        if rid:
            delegate_to = rid
            break
    out = {
        "user_message": um,
        "has_delegatee": bool(delegate_to),
        "delegate_to": delegate_to,
    }
    return {"data": out}, state


def register_rag_pick_delegatee() -> None:
    register_unit(
        UnitSpec(
            type_name="RagPickDelegatee",
            input_ports=RAG_PICK_DELEGATEE_INPUT_PORTS,
            output_ports=RAG_PICK_DELEGATEE_OUTPUT_PORTS,
            step_fn=_rag_pick_delegatee_step,
            environment_tags=["canonical"],
            environment_tags_are_agnostic=True,
            runtime_scope=None,
            description=(
                "From RunWorkflow RAG outputs, pick first TeamMember chunk → delegate_to role id; "
                "pass user_message through for downstream PayloadTransform."
            ),
        )
    )


__all__ = [
    "RAG_PICK_DELEGATEE_INPUT_PORTS",
    "RAG_PICK_DELEGATEE_OUTPUT_PORTS",
    "register_rag_pick_delegatee",
]
