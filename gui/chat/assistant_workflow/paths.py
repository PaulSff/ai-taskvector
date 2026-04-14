"""Paths and defaults for role chat workflows and tool follow-up workflows."""
from __future__ import annotations

from assistants.roles import WORKFLOW_DESIGNER_ROLE_ID
from assistants.roles.workflow_path import get_role_chat_workflow_path
from assistants.tools.workflow_path import get_tool_workflow_path

# Default when ``workflow_path`` is omitted from ``run_assistant_workflow`` (Workflow Designer chat graph).
ASSISTANT_WORKFLOW_PATH = get_role_chat_workflow_path(WORKFLOW_DESIGNER_ROLE_ID)

WEB_SEARCH_WORKFLOW_PATH = get_tool_workflow_path("web_search")
BROWSER_WORKFLOW_PATH = get_tool_workflow_path("browse")
GITHUB_GET_WORKFLOW_PATH = get_tool_workflow_path("github")

# Timeout so we don't hang when a unit (LLM, RAG, etc.) never responds.
DEFAULT_EXECUTION_TIMEOUT_S = 300.0
