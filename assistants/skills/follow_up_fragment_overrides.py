"""
Map ``config/prompts/workflow_designer.json`` ``fragments`` keys to skill ``follow_ups`` module attributes.

Applied from ``assistants.prompts`` after defaults load so deployments can override strings without editing Python.
"""
from __future__ import annotations

import importlib
from typing import Any

# (json fragments key, module path, attribute name on that module)
_WORKFLOW_DESIGNER_SKILL_FRAGMENT_MAP: tuple[tuple[str, str, str], ...] = (
    ("request_file_content_follow_up_prefix", "assistants.skills.read_file.follow_ups", "REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX"),
    ("request_file_content_follow_up_suffix", "assistants.skills.read_file.follow_ups", "REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX"),
    ("read_code_block_follow_up_prefix", "assistants.skills.read_code_block.follow_ups", "READ_CODE_BLOCK_FOLLOW_UP_PREFIX"),
    ("read_code_block_follow_up_suffix", "assistants.skills.read_code_block.follow_ups", "READ_CODE_BLOCK_FOLLOW_UP_SUFFIX"),
    ("read_code_block_follow_up_user_message", "assistants.skills.read_code_block.follow_ups", "READ_CODE_BLOCK_FOLLOW_UP_USER_MESSAGE"),
    ("run_workflow_follow_up_prefix", "assistants.skills.run_workflow.follow_ups", "RUN_WORKFLOW_FOLLOW_UP_PREFIX"),
    ("run_workflow_follow_up_suffix", "assistants.skills.run_workflow.follow_ups", "RUN_WORKFLOW_FOLLOW_UP_SUFFIX"),
    ("grep_follow_up_prefix", "assistants.skills.grep.follow_ups", "GREP_FOLLOW_UP_PREFIX"),
    ("grep_follow_up_suffix", "assistants.skills.grep.follow_ups", "GREP_FOLLOW_UP_SUFFIX"),
    ("rag_follow_up_prefix", "assistants.skills.rag_search.follow_ups", "RAG_SEARCH_FOLLOW_UP_PREFIX"),
    ("rag_follow_up_suffix", "assistants.skills.rag_search.follow_ups", "RAG_SEARCH_FOLLOW_UP_SUFFIX"),
    ("web_search_follow_up_prefix", "assistants.skills.web_search.follow_ups", "WEB_SEARCH_FOLLOW_UP_PREFIX"),
    ("web_search_follow_up_suffix", "assistants.skills.web_search.follow_ups", "WEB_SEARCH_FOLLOW_UP_SUFFIX"),
    ("browse_follow_up_prefix", "assistants.skills.browse.follow_ups", "BROWSE_FOLLOW_UP_PREFIX"),
    ("browse_follow_up_suffix", "assistants.skills.browse.follow_ups", "BROWSE_FOLLOW_UP_SUFFIX"),
    ("github_follow_up_prefix", "assistants.skills.github.follow_ups", "GITHUB_FOLLOW_UP_PREFIX"),
    ("github_follow_up_suffix", "assistants.skills.github.follow_ups", "GITHUB_FOLLOW_UP_SUFFIX"),
    ("tool_empty_result_line", "assistants.skills.follow_up_common", "TOOL_EMPTY_RESULT_LINE"),
    ("tool_empty_user_message", "assistants.skills.follow_up_common", "TOOL_EMPTY_USER_MESSAGE"),
)


def apply_workflow_designer_json_skill_fragments(fragments: dict[str, Any]) -> None:
    """Set attributes on skill ``follow_ups`` modules when keys exist in ``fragments``."""
    if not fragments:
        return
    for key, mod_path, attr in _WORKFLOW_DESIGNER_SKILL_FRAGMENT_MAP:
        if key not in fragments:
            continue
        val = fragments[key]
        if not isinstance(val, str):
            continue
        mod = importlib.import_module(mod_path)
        setattr(mod, attr, val)
