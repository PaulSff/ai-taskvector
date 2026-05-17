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

# Default regex (can be overridden via params["role_path_regex"])
DEFAULT_ROLE_PATH_RE = re.compile(r"/taskvector/([^/]+)/ROLE\.md$", re.IGNORECASE)

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


def _compile_role_path_re(params: dict[str, Any]) -> re.Pattern:
    """
    Compile a regex from params["role_path_regex"] if provided and valid,
    otherwise return the default pattern.
    """
    pat = params.get("role_path_regex") if isinstance(params, dict) else None
    if isinstance(pat, str) and pat:
        try:
            return re.compile(pat, re.IGNORECASE)
        except Exception:
            pass
    return DEFAULT_ROLE_PATH_RE


def _role_id_from_row(row: Any, role_path_re: re.Pattern) -> str | None:
    """
    Identification: only use metadata.file_path matched against role_path_re.
    role_path_re should capture the role id in group(1).
    """
    if not isinstance(row, dict):
        return None
    meta_val = row.get("metadata")
    meta = meta_val if isinstance(meta_val, dict) else {}
    fp_val = meta.get("file_path")
    if not fp_val:
        return None
    fp = str(fp_val).replace("\\", "/")
    m = role_path_re.search(fp)
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
    role_path_re = _compile_role_path_re(params or {})
    for row in rows:
        rid = _role_id_from_row(row, role_path_re)
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
            environment_tags=["rag"],
            environment_tags_are_agnostic=True,
            runtime_scope=None,
            description=(
                "From RunWorkflow RAG outputs, pick first TeamMember row by metadata.file_path "
                "matching a configurable regex (params['role_path_regex'], default "
                r"'/taskvector/([^/]+)/ROLE\\.md$') → delegate_to role id; pass user_message through."
            ),
        )
    )


__all__ = [
    "RAG_PICK_DELEGATEE_INPUT_PORTS",
    "RAG_PICK_DELEGATEE_OUTPUT_PORTS",
    "register_rag_pick_delegatee",
]
