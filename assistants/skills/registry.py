"""
Register skill implementations by stable id (Phase 2+).

Follow-up runners are async callables::
    async def run(ctx, po, *, language_hint) -> FollowUpContribution
"""
from __future__ import annotations

from typing import Any

# Populated as skills are extracted from workflow_designer_followups.py
SKILLS: dict[str, Any] = {}
_BUILTIN_SKILLS_LOADED = False


def _ensure_builtin_follow_up_skills() -> None:
    global _BUILTIN_SKILLS_LOADED
    if _BUILTIN_SKILLS_LOADED:
        return
    from assistants.skills.browse import run_browse_follow_up
    from assistants.skills.github import run_github_follow_up
    from assistants.skills.grep import run_grep_follow_up
    from assistants.skills.rag_search import run_rag_search_follow_up
    from assistants.skills.read_code_block import run_read_code_block_follow_up
    from assistants.skills.read_file import run_read_file_follow_up
    from assistants.skills.report import run_report_follow_up
    from assistants.skills.run_workflow import run_run_workflow_follow_up
    from assistants.skills.web_search import run_web_search_follow_up

    SKILLS["read_code_block"] = run_read_code_block_follow_up
    SKILLS["run_workflow"] = run_run_workflow_follow_up
    SKILLS["grep"] = run_grep_follow_up
    SKILLS["read_file"] = run_read_file_follow_up
    SKILLS["rag_search"] = run_rag_search_follow_up
    SKILLS["web_search"] = run_web_search_follow_up
    SKILLS["browse"] = run_browse_follow_up
    SKILLS["github"] = run_github_follow_up
    SKILLS["report"] = run_report_follow_up
    _BUILTIN_SKILLS_LOADED = True


def get_follow_up_runner(skill_id: str) -> Any:
    """Return registered follow-up coroutine function, or None."""
    _ensure_builtin_follow_up_skills()
    impl = SKILLS.get((skill_id or "").strip())
    return impl if callable(impl) else None


def register_skill(skill_id: str, impl: Any) -> None:
    """Register or replace a skill implementation."""
    sid = (skill_id or "").strip()
    if not sid:
        raise ValueError("skill_id is required")
    SKILLS[sid] = impl


def list_skill_ids() -> tuple[str, ...]:
    _ensure_builtin_follow_up_skills()
    return tuple(sorted(SKILLS.keys()))


def clear_skill_registry_for_tests() -> None:
    """Drop builtins so tests can isolate registry state (tests only)."""
    global _BUILTIN_SKILLS_LOADED
    SKILLS.clear()
    _BUILTIN_SKILLS_LOADED = False
