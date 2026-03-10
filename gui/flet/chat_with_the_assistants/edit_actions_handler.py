"""
Orchestrate Workflow Designer edit-action follow-ups: request_file_content, rag_search_results, import_workflow.

Runs the follow-up turns (read file / inject search results / import success message, call LLM, re-parse)
so chat.py stays thin. Returns the final result and latest content for the chat to apply and branch on.
"""
from __future__ import annotations

from typing import Any, Callable

from assistants.process_assistant import graph_summary
from gui.flet.chat_with_the_assistants.workflow_designer_handler import (
    build_workflow_designer_system_prompt,
    handle_workflow_edits_response,
)
from assistants.prompts import (
    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP,
    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP,
    WORKFLOW_DESIGNER_BROWSE_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_BROWSE_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP,
    WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_SELF_CORRECTION,
    WORKFLOW_DESIGNER_TODO_FOLLOW_UP,
    WORKFLOW_DESIGNER_WEB_SEARCH_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_WEB_SEARCH_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_SYSTEM,
)

_TODO_ACTIONS = frozenset({"add_todo_list", "remove_todo_list", "add_task", "remove_task", "mark_completed"})


async def run_workflow_designer_follow_ups(
    result: dict[str, Any],
    content: str,
    get_graph: Callable[[], Any],
    user_message: str,
    last_apply_result_ref: list,
    *,
    run_llm: Callable[[list[dict[str, str]]], Any],
    get_history_messages: Callable[[], list[dict[str, str]]],
    read_file: Callable[[str, Any, Any, Any], str | None],
    mydata_dir: Any,
    units_dir: Any,
    repo_root: Any,
    set_status: Callable[[str | None], None],
    apply_fn: Callable[[Any], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> tuple[dict[str, Any], str]:
    """
    Run request_file_content loop, then rag_search_results follow-up, then import_workflow follow-up if applied.
    run_llm(messages) is async and returns the new assistant content.
    read_file(path, mydata_dir, units_dir, repo_root) returns file content or None.
    apply_fn(graph) updates the current graph (used in import_workflow follow-up so get_graph() sees new graph).
    Returns (final_result, latest_content). Chat should still apply result["graph"] when result["kind"] == "applied".
    """
    def _apply_result(r: dict[str, Any]) -> None:
        last_apply_result_ref[0] = r["last_apply_result"]

    def _build_system() -> str:
        return build_workflow_designer_system_prompt(
            graph_summary(get_graph()),
            last_apply_result_ref[0],
            base_prompt=WORKFLOW_DESIGNER_SYSTEM,
            self_correction_template=WORKFLOW_DESIGNER_SELF_CORRECTION,
            recent_changes=None,
            rag_context=None,
        )

    # 1) request_file_content loop
    while result.get("request_file_content"):
        contents = []
        for path in result["request_file_content"]:
            c = read_file(path, mydata_dir, units_dir, repo_root)
            if c:
                contents.append((path, c))
        if not contents:
            break
        file_content_msg = WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX
        for path, c in contents:
            file_content_msg += f"--- {path} ---\n{c}\n\n"
        file_content_msg += WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX + user_message
        followup_msgs = (
            [{"role": "system", "content": _build_system()}]
            + get_history_messages()
            + [{"role": "user", "content": user_message}]
            + [{"role": "assistant", "content": content}]
            + [{"role": "user", "content": file_content_msg}]
        )
        set_status("Reading file and continuing…")
        content = await run_llm(followup_msgs)
        if is_cancelled and is_cancelled():
            return result, content
        set_status("Applying edits…")
        result = handle_workflow_edits_response(content, get_graph())
        _apply_result(result)

    # 2) rag_search_results single follow-up
    if result.get("rag_search_results"):
        search_msg = (
            "Relevant context from knowledge base (you requested search):\n\n"
            + result["rag_search_results"]
            + "\n\nUser request: " + user_message
        )
        followup_msgs = (
            [{"role": "system", "content": _build_system()}]
            + get_history_messages()
            + [{"role": "user", "content": user_message}]
            + [{"role": "assistant", "content": content}]
            + [{"role": "user", "content": search_msg}]
        )
        set_status("Searching knowledge base…")
        content = await run_llm(followup_msgs)
        if is_cancelled and is_cancelled():
            return result, content
        set_status("Applying edits…")
        result = handle_workflow_edits_response(content, get_graph())
        _apply_result(result)

    # 2b) read_code_block_results single follow-up
    if result.get("read_code_block_results"):
        code_block_msg = (
            WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_PREFIX
            + result["read_code_block_results"]
            + WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_SUFFIX
            + user_message
        )
        followup_msgs = (
            [{"role": "system", "content": _build_system()}]
            + get_history_messages()
            + [{"role": "user", "content": user_message}]
            + [{"role": "assistant", "content": content}]
            + [{"role": "user", "content": code_block_msg}]
        )
        set_status("Reading code block…")
        content = await run_llm(followup_msgs)
        if is_cancelled and is_cancelled():
            return result, content
        set_status("Applying edits…")
        result = handle_workflow_edits_response(content, get_graph())
        _apply_result(result)

    # 2c) web_search_results single follow-up
    if result.get("web_search_results"):
        web_search_msg = (
            WORKFLOW_DESIGNER_WEB_SEARCH_FOLLOW_UP_PREFIX
            + result["web_search_results"]
            + WORKFLOW_DESIGNER_WEB_SEARCH_FOLLOW_UP_SUFFIX
            + user_message
        )
        followup_msgs = (
            [{"role": "system", "content": _build_system()}]
            + get_history_messages()
            + [{"role": "user", "content": user_message}]
            + [{"role": "assistant", "content": content}]
            + [{"role": "user", "content": web_search_msg}]
        )
        set_status("Searching web…")
        content = await run_llm(followup_msgs)
        if is_cancelled and is_cancelled():
            return result, content
        set_status("Applying edits…")
        result = handle_workflow_edits_response(content, get_graph())
        _apply_result(result)

    # 2d) browse_results single follow-up
    if result.get("browse_results"):
        browse_msg = (
            WORKFLOW_DESIGNER_BROWSE_FOLLOW_UP_PREFIX
            + result["browse_results"]
            + WORKFLOW_DESIGNER_BROWSE_FOLLOW_UP_SUFFIX
            + user_message
        )
        followup_msgs = (
            [{"role": "system", "content": _build_system()}]
            + get_history_messages()
            + [{"role": "user", "content": user_message}]
            + [{"role": "assistant", "content": content}]
            + [{"role": "user", "content": browse_msg}]
        )
        set_status("Loading page…")
        content = await run_llm(followup_msgs)
        if is_cancelled and is_cancelled():
            return result, content
        set_status("Applying edits…")
        result = handle_workflow_edits_response(content, get_graph())
        _apply_result(result)

    # 3) import_workflow follow-up (after we've applied)
    if result.get("kind") == "applied" and apply_fn is not None:
        had_import_workflow = any(
            e.get("action") == "import_workflow"
            for e in result.get("edits", [])
        )
        if had_import_workflow:
            apply_fn(result["graph"])
            import_followup_msg = WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP + user_message
            followup_msgs = (
                [{"role": "system", "content": _build_system()}]
                + get_history_messages()
                + [{"role": "user", "content": user_message}]
                + [{"role": "assistant", "content": content}]
                + [{"role": "user", "content": import_followup_msg}]
            )
            set_status("Reviewing…")
            content = await run_llm(followup_msgs)
            if is_cancelled and is_cancelled():
                return result, content
            set_status("Applying edits…")
            result = handle_workflow_edits_response(content, get_graph())
            _apply_result(result)
            if result.get("kind") == "applied":
                apply_fn(result["graph"])
            set_status(None)

    # 4) add_comment and/or TODO list follow-up (same pattern: apply, then one follow-up turn)
    if result.get("kind") == "applied" and apply_fn is not None:
        edits = result.get("edits") or []
        had_add_comment = any(e.get("action") == "add_comment" for e in edits)
        had_todo = any(e.get("action") in _TODO_ACTIONS for e in edits)
        if had_add_comment or had_todo:
            apply_fn(result["graph"])
            if had_add_comment and had_todo:
                followup_msg = WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP + user_message
            elif had_add_comment:
                followup_msg = WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP + user_message
            else:
                followup_msg = WORKFLOW_DESIGNER_TODO_FOLLOW_UP + user_message
            followup_msgs = (
                [{"role": "system", "content": _build_system()}]
                + get_history_messages()
                + [{"role": "user", "content": user_message}]
                + [{"role": "assistant", "content": content}]
                + [{"role": "user", "content": followup_msg}]
            )
            set_status("Reviewing…")
            content = await run_llm(followup_msgs)
            if is_cancelled and is_cancelled():
                return result, content
            set_status("Applying edits…")
            result = handle_workflow_edits_response(content, get_graph())
            _apply_result(result)
            if result.get("kind") == "applied":
                apply_fn(result["graph"])
            set_status(None)

    return result, content
