"""
Register follow-up tool implementations by stable id (Phase 2+).

Follow-up runners are async callables::
    async def run(ctx, po, *, language_hint) -> FollowUpContribution
"""
from __future__ import annotations

from typing import Any

# Maps tool_id -> follow-up coroutine (populated when builtins load).
TOOL_RUNNERS: dict[str, Any] = {}
_BUILTIN_TOOLS_LOADED = False


def _ensure_builtin_follow_up_tools() -> None:
    global _BUILTIN_TOOLS_LOADED
    if _BUILTIN_TOOLS_LOADED:
        return
    from assistants.tools.add_comment import run_add_comment_follow_up
    from assistants.tools.browse import run_browse_follow_up
    from assistants.tools.github import run_github_follow_up
    from assistants.tools.grep import run_grep_follow_up
    from assistants.tools.rag_search import run_rag_search_follow_up
    from assistants.tools.read_code_block import run_read_code_block_follow_up
    from assistants.tools.read_file import run_read_file_follow_up
    from assistants.tools.report import run_report_follow_up
    from assistants.tools.todo_manager import run_todo_manager_follow_up
    from assistants.tools.run_workflow import run_run_workflow_follow_up
    from assistants.tools.web_search import run_web_search_follow_up

    TOOL_RUNNERS["read_code_block"] = run_read_code_block_follow_up
    TOOL_RUNNERS["run_workflow"] = run_run_workflow_follow_up
    TOOL_RUNNERS["grep"] = run_grep_follow_up
    TOOL_RUNNERS["read_file"] = run_read_file_follow_up
    TOOL_RUNNERS["rag_search"] = run_rag_search_follow_up
    TOOL_RUNNERS["web_search"] = run_web_search_follow_up
    TOOL_RUNNERS["browse"] = run_browse_follow_up
    TOOL_RUNNERS["github"] = run_github_follow_up
    TOOL_RUNNERS["report"] = run_report_follow_up
    TOOL_RUNNERS["add_comment"] = run_add_comment_follow_up
    TOOL_RUNNERS["todo_manager"] = run_todo_manager_follow_up
    _BUILTIN_TOOLS_LOADED = True


def get_follow_up_runner(tool_id: str) -> Any:
    """Return registered follow-up coroutine function, or None."""
    _ensure_builtin_follow_up_tools()
    impl = TOOL_RUNNERS.get((tool_id or "").strip())
    return impl if callable(impl) else None


def register_tool(tool_id: str, impl: Any) -> None:
    """Register or replace a tool implementation."""
    tid = (tool_id or "").strip()
    if not tid:
        raise ValueError("tool_id is required")
    TOOL_RUNNERS[tid] = impl


def list_tool_ids() -> tuple[str, ...]:
    _ensure_builtin_follow_up_tools()
    return tuple(sorted(TOOL_RUNNERS.keys()))


def clear_tool_registry_for_tests() -> None:
    """Drop builtins so tests can isolate registry state (tests only)."""
    global _BUILTIN_TOOLS_LOADED
    TOOL_RUNNERS.clear()
    _BUILTIN_TOOLS_LOADED = False
