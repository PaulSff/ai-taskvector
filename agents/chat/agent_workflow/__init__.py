"""
Shared execution and helpers for role chat workflows (merge_response contract).

Role-specific runners (e.g. dev-mode in-memory graph, RL training injects) live under
``gui.chat.role_turns.<role>.workflow_runner``.
"""

from __future__ import annotations

from .helpers import (
    build_agent_workflow_unit_param_overrides,
    build_self_correction_retry_inputs,
    get_runtime_for_prompts,
    refresh_last_apply_result_after_canvas_apply,
)
from .paths import (
    BROWSER_WORKFLOW_PATH,
    CALENDAR_WORKFLOW_PATH,
    CLONE_ROLE_WORKFLOW_PATH,
    DEFAULT_EXECUTION_TIMEOUT_S,
    DELETE_WORKFLOW_PATH,
    EDIT_FILE_WORKFLOW_PATH,
    GET_CHATS_WORKFLOW_PATH,
    GITHUB_GET_WORKFLOW_PATH,
    GREP_WORKFLOW_PATH,
    LIST_DIR_WORKFLOW_PATH,
    MAKE_DIR_WORKFLOW_PATH,
    NEW_FILE_WORKFLOW_PATH,
    RAG_SEARCH_WORKFLOW_PATH,
    RENAME_WORKFLOW_PATH,
    SEND_MESSAGE_WORKFLOW_PATH,
    WEB_SEARCH_WORKFLOW_PATH,
    agent_WORKFLOW_PATH,
)
from .run_agent_workflow import run_agent_workflow
from .run_tool_workflow import run_workflow_with_errors

__all__ = [
    "BROWSER_WORKFLOW_PATH",
    "CALENDAR_WORKFLOW_PATH",
    "CLONE_ROLE_WORKFLOW_PATH",
    "DEFAULT_EXECUTION_TIMEOUT_S",
    "DELETE_WORKFLOW_PATH",
    "EDIT_FILE_WORKFLOW_PATH",
    "GET_CHATS_WORKFLOW_PATH",
    "GITHUB_GET_WORKFLOW_PATH",
    "GREP_WORKFLOW_PATH",
    "LIST_DIR_WORKFLOW_PATH",
    "MAKE_DIR_WORKFLOW_PATH",
    "NEW_FILE_WORKFLOW_PATH",
    "RAG_SEARCH_WORKFLOW_PATH",
    "RENAME_WORKFLOW_PATH",
    "SEND_MESSAGE_WORKFLOW_PATH",
    "WEB_SEARCH_WORKFLOW_PATH",
    "agent_WORKFLOW_PATH",
    "build_agent_workflow_unit_param_overrides",
    "build_self_correction_retry_inputs",
    "get_runtime_for_prompts",
    "refresh_last_apply_result_after_canvas_apply",
    "run_agent_workflow",
    "run_workflow_with_errors",
]
