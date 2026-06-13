"""Paths and defaults for role chat workflows and tool follow-up workflows."""

from __future__ import annotations

from agents.roles import WORKFLOW_DESIGNER_ROLE_ID
from agents.roles.workflow_path import get_role_chat_workflow_path
from agents.tools.workflow_path import get_tool_workflow_path

# Default when ``workflow_path`` is omitted from ``run_agent_workflow`` (Workflow Designer chat graph).
agent_WORKFLOW_PATH = get_role_chat_workflow_path(WORKFLOW_DESIGNER_ROLE_ID)

WEB_SEARCH_WORKFLOW_PATH = get_tool_workflow_path("web_search")
BROWSER_WORKFLOW_PATH = get_tool_workflow_path("browse")
GITHUB_GET_WORKFLOW_PATH = get_tool_workflow_path("github")
GET_CHATS_WORKFLOW_PATH = get_tool_workflow_path("get_chats")
SEND_MESSAGE_WORKFLOW_PATH = get_tool_workflow_path("send_message")

# Timeout so we don't hang when a unit (LLM, RAG, etc.) never responds.
DEFAULT_EXECUTION_TIMEOUT_S = 300.0
