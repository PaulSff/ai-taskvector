"""
Shared execution and helpers for role chat workflows (merge_response contract).

Role-specific runners (e.g. dev-mode in-memory graph, RL training injects) live under
``gui.chat.role_turns.<role>.workflow_runner``.
"""
from __future__ import annotations

from .helpers import (
    build_assistant_workflow_unit_param_overrides,
    build_self_correction_retry_inputs,
    get_runtime_for_prompts,
    refresh_last_apply_result_after_canvas_apply,
    run_workflow_with_errors,
)
from .paths import (
    ASSISTANT_WORKFLOW_PATH,
    BROWSER_WORKFLOW_PATH,
    DEFAULT_EXECUTION_TIMEOUT_S,
    GITHUB_GET_WORKFLOW_PATH,
    WEB_SEARCH_WORKFLOW_PATH,
)
from .run import run_assistant_workflow

__all__ = [
    "ASSISTANT_WORKFLOW_PATH",
    "BROWSER_WORKFLOW_PATH",
    "DEFAULT_EXECUTION_TIMEOUT_S",
    "GITHUB_GET_WORKFLOW_PATH",
    "WEB_SEARCH_WORKFLOW_PATH",
    "build_assistant_workflow_unit_param_overrides",
    "build_self_correction_retry_inputs",
    "get_runtime_for_prompts",
    "refresh_last_apply_result_after_canvas_apply",
    "run_assistant_workflow",
    "run_workflow_with_errors",
]
