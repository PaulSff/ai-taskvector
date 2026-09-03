"""
Register follow-up tool implementations by stable id (Phase 2+).

Follow-up runners have this signature::

    async def run(
        ctx,
        po,
        *,
        language_hint,
    ) -> FollowUpContribution
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol

from agents.tools.types import ToolList
from core.schemas.primitives import Data

if TYPE_CHECKING:
    from agents.chat.context.follow_up_context import (
        ParserFollowUpContext,
    )
    from agents.tools.types import (
        FollowUpContribution,
    )


class FollowUpRunner(Protocol):
    def __call__(
        self,
        ctx: ParserFollowUpContext,
        po: Data,
        *,
        language_hint: Callable[[], str],
    ) -> Awaitable[FollowUpContribution]:
        ...

# Maps tool_id -> follow-up coroutine.
TOOL_RUNNERS: dict[str, FollowUpRunner] = {}

_builtin_tools_loaded = False


def _ensure_builtin_follow_up_tools() -> None:
    global _builtin_tools_loaded

    if _builtin_tools_loaded:
        return

    from agents.tools.add_comment import run_add_comment_follow_up
    from agents.tools.browse import run_browse_follow_up
    from agents.tools.calendar import run_calendar_follow_up
    from agents.tools.clone_role import run_clone_role_follow_up
    from agents.tools.delete import run_delete_file_follow_up
    from agents.tools.edit_file import run_edit_file_follow_up
    from agents.tools.formulas_calc import run_formulas_calc_follow_up
    from agents.tools.get_chats import run_get_chats_follow_up
    from agents.tools.github import run_github_follow_up
    from agents.tools.grep import run_grep_follow_up
    from agents.tools.list_dir import run_list_dir_follow_up
    from agents.tools.make_dir import run_make_dir_follow_up
    from agents.tools.new_file import run_new_file_follow_up
    from agents.tools.rag_search import run_rag_search_follow_up
    from agents.tools.read_code_block import run_read_code_block_follow_up
    from agents.tools.read_current_workflow import (
        run_read_current_workflow_follow_up,
    )
    from agents.tools.read_file import run_read_file_follow_up
    from agents.tools.rename import run_rename_follow_up
    from agents.tools.report import run_report_follow_up
    from agents.tools.run_workflow import run_run_workflow_follow_up
    from agents.tools.send_message import run_send_message_follow_up
    from agents.tools.todo_manager import run_todo_manager_follow_up
    from agents.tools.web_search import run_web_search_follow_up

    TOOL_RUNNERS.update(
        {
            "read_code_block": run_read_code_block_follow_up,
            "read_current_workflow": run_read_current_workflow_follow_up,
            "run_workflow": run_run_workflow_follow_up,
            "grep": run_grep_follow_up,
            "read_file": run_read_file_follow_up,
            "formulas_calc": run_formulas_calc_follow_up,
            "rag_search": run_rag_search_follow_up,
            "web_search": run_web_search_follow_up,
            "browse": run_browse_follow_up,
            "github": run_github_follow_up,
            "report": run_report_follow_up,
            "add_comment": run_add_comment_follow_up,
            "todo_manager": run_todo_manager_follow_up,
            "get_chats": run_get_chats_follow_up,
            "send_message": run_send_message_follow_up,
            "calendar": run_calendar_follow_up,
            "clone_role": run_clone_role_follow_up,
            "list_dir": run_list_dir_follow_up,
            "new_file": run_new_file_follow_up,
            "edit_file": run_edit_file_follow_up,
            "delete": run_delete_file_follow_up,
            "make_dir": run_make_dir_follow_up,
            "rename": run_rename_follow_up,
        }.items()
    )


    _builtin_tools_loaded = True


def get_follow_up_runner(tool_id: str) -> FollowUpRunner | None:
    """Return the registered follow-up coroutine, or None."""
    _ensure_builtin_follow_up_tools()
    return TOOL_RUNNERS.get((tool_id or "").strip())


def register_tool(tool_id: str, impl: FollowUpRunner) -> None:
    """Register or replace a follow-up tool implementation."""
    tid = tool_id.strip()

    if not tid:
        raise ValueError("tool_id is required")

    TOOL_RUNNERS[tid] = impl


def list_tool_ids() -> ToolList:
    _ensure_builtin_follow_up_tools()
    return tuple(sorted(TOOL_RUNNERS))


def clear_tool_registry_for_tests() -> None:
    """Drop builtins so tests can isolate registry state."""
    global _builtin_tools_loaded

    TOOL_RUNNERS.clear()
    _builtin_tools_loaded = False
