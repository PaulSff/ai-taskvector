"""
Workflow Designer: parser-output tool follow-up chain and post-apply review rounds.

Orchestrates RAG/web/browse/grep/GitHub/read_file/read_code_block/run_workflow/report handling
and re-runs assistant_workflow; then optional post-apply assistant rounds (import/todo/comment).
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import flet as ft

from assistants.prompts import (
    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP,
    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP,
    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_BROWSE_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_BROWSE_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_DEFAULT_POST_APPLY_FOLLOW_UP,
    WORKFLOW_DESIGNER_DEFAULT_POST_APPLY_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_GITHUB_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_GITHUB_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_GREP_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_GREP_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP,
    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_RAG_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_RAG_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_TODO_FOLLOW_UP,
    WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_WEB_SEARCH_FOLLOW_UP_PREFIX,
    WORKFLOW_DESIGNER_WEB_SEARCH_FOLLOW_UP_SUFFIX,
    WORKFLOW_DESIGNER_TOOL_EMPTY_RESULT_LINE,
    WORKFLOW_DESIGNER_TOOL_EMPTY_USER_MESSAGE,
)
from gui.flet.chat_with_the_assistants.language_control import (
    default_wf_language_hint,
    maybe_pin_session_language_from_workflow_response,
)
from gui.flet.chat_with_the_assistants.rag_context import get_rag_context, get_rag_context_by_path
from gui.flet.chat_with_the_assistants.todo_list_manager import get_summary_params
from gui.flet.chat_with_the_assistants.workflow_designer_handler import (
    BROWSER_WORKFLOW_PATH,
    GITHUB_GET_WORKFLOW_PATH,
    WEB_SEARCH_WORKFLOW_PATH,
    build_assistant_workflow_initial_inputs,
    run_assistant_workflow,
    refresh_last_apply_result_after_canvas_apply,
    run_workflow_with_errors,
)
from gui.flet.components.settings import get_coding_is_allowed
from gui.flet.components.workflow.core_workflows import validate_graph_to_apply_for_canvas
from gui.flet.tools.workflow_output_normalizer import normalize_follow_up_parser_output
from units.web import register_web_units


def workflow_merge_response_apply_failed(resp: dict[str, Any]) -> bool:
    """True when ApplyEdits reported a failed apply (merge_response result/status from process unit)."""
    r = resp.get("result") or {}
    if r.get("kind") == "apply_failed":
        return True
    st = resp.get("status")
    if isinstance(st, dict) and st.get("attempted") is True and st.get("success") is False:
        return True
    return False


def merge_preserved_apply_failure_into_response(
    response: dict[str, Any],
    preserved: dict[str, Any],
) -> dict[str, Any]:
    """Restore result/status/workflow_errors from an earlier run in the same follow-up chain."""
    out = dict(response)
    out["result"] = dict(preserved.get("result") or {})
    st = preserved.get("status")
    out["status"] = dict(st) if isinstance(st, dict) else st
    merged_errs = list(response.get("workflow_errors") or [])
    for e in preserved.get("workflow_errors") or []:
        if e not in merged_errs:
            merged_errs.append(e)
    out["workflow_errors"] = merged_errs
    return out


def workflow_response_is_question(resp: dict[str, Any]) -> bool:
    """True when assistant workflow classified the current reply as a user question."""
    v = resp.get("is_question")
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y")
    return False


@dataclass
class ParserFollowUpContext:
    """Bindings for run_parser_output_follow_up_chain (GUI + session state)."""

    page: ft.Page
    graph_ref: list[Any]
    state: Any
    token: Any
    turn_id: str
    assistant_label: str
    follow_up_contexts: list[str]
    max_rounds: int
    wf_language_hint: list[str]
    is_current_run: Callable[[Any], bool]
    toast: Callable[[str], Awaitable[None]]
    set_inline_status: Callable[[str | None], None]
    append_message: Callable[..., None]
    prepare_stream_row: Callable[[], None]
    normalize_user_message_for_workflow: Callable[[str], str]
    last_apply_result_ref: list[Any]
    get_recent_changes: Callable[[], str | None] | None
    overrides: dict[str, Any]
    run_workflow_streaming: Callable[..., Awaitable[Any]]
    get_runtime_for_prompts: Callable[[Any], str]
    format_previous_turn: Callable[[list[Any]], str]
    on_show_run_console: Callable[..., None] | None = None


async def run_parser_output_follow_up_chain(
    ctx: ParserFollowUpContext,
    resp: dict[str, Any],
) -> dict[str, Any] | None:
    """
    If parser_output requests tools, fetch context and re-run assistant_workflow.
    Returns None when the user cancelled the run mid-chain.
    """
    def _hint() -> str:
        return ctx.wf_language_hint[0]

    maybe_pin_session_language_from_workflow_response(ctx.state, resp)
    ctx.wf_language_hint[0] = default_wf_language_hint(ctx.state.session_language)
    preserved_apply_failure: dict[str, Any] | None = None

    def _capture_apply_failure(r: dict[str, Any]) -> None:
        nonlocal preserved_apply_failure
        if not workflow_merge_response_apply_failed(r):
            return
        preserved_apply_failure = {
            "result": dict(r.get("result") or {}),
            "status": dict(r.get("status") or {})
            if isinstance(r.get("status"), dict)
            else r.get("status"),
            "workflow_errors": list(r.get("workflow_errors") or []),
        }

    response = resp
    _capture_apply_failure(resp)
    if workflow_response_is_question(response):
        # Assistant asked the user a question; do not auto-run tool follow-up turns.
        return response
    for _ in range(ctx.max_rounds):
        po = normalize_follow_up_parser_output(response.get("parser_output"))
        context_chunks: list[str] = []
        follow_up_msg = WORKFLOW_DESIGNER_FOLLOW_UP_USER_MESSAGE.format(
            language=_hint(),
            session_language=_hint(),
        )
        any_empty_tool = False
        read_code_ids_for_msg: list[str] = []

        if po.get("read_code_block_ids"):
            ids = list(po.get("read_code_block_ids") or [])
            read_code_ids_for_msg = ids
            if ctx.graph_ref[0]:
                ctx.set_inline_status("Adding task and re-running…")
                from gui.flet.chat_with_the_assistants.todo_list_manager import add_tasks_for_read_code_block

                _g = ctx.graph_ref[0]
                _g_dict = _g.model_dump(by_alias=True) if hasattr(_g, "model_dump") else (_g if isinstance(_g, dict) else _g)
                updated = add_tasks_for_read_code_block(ids, _g_dict)
                if hasattr(ctx.graph_ref[0], "model_dump"):
                    vg, v_err = validate_graph_to_apply_for_canvas(updated)
                    if v_err or vg is None:
                        if ctx.is_current_run(ctx.token):
                            await ctx.toast(f"Graph validation failed: {(v_err or '')[:120]}")
                    else:
                        ctx.graph_ref[0] = vg
                else:
                    ctx.graph_ref[0] = updated
                context_chunks.append(
                    WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_PREFIX.rstrip()
                    + " The source for the requested unit(s) is included in the graph summary.\n"
                    + WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_SUFFIX.format(
                        language=_hint(),
                        session_language=_hint(),
                    )
                )
            else:
                context_chunks.append(
                    WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_PREFIX.rstrip()
                    + " No graph is loaded in the designer; unit source cannot be read from the graph until a graph is available.\n"
                    + WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_SUFFIX.format(
                        language=_hint(),
                        session_language=_hint(),
                    )
                )

        if po.get("run_workflow"):
            ctx.set_inline_status("Workflow run result…")
            run_out = response.get("run_output")
            chunk: str | None = None
            if ctx.on_show_run_console and isinstance(run_out, dict):
                try:
                    ctx.on_show_run_console(run_out)
                except Exception:
                    pass
            if isinstance(run_out, dict):
                data = run_out.get("data")
                err = run_out.get("error")
                parts = []
                if data is not None:
                    try:
                        parts.append(json.dumps(data, indent=2, ensure_ascii=False))
                    except Exception:
                        parts.append(str(data))
                if isinstance(err, str) and err.strip():
                    parts.append(f"Error: {err}")
                if parts:
                    chunk = (
                        WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_PREFIX
                        + "\n".join(parts)
                        + WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_SUFFIX.format(
                            language=_hint(),
                            session_language=_hint(),
                        )
                    )
            elif run_out is not None:
                chunk = (
                    WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_PREFIX
                    + str(run_out)
                    + WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_SUFFIX.format(
                        language=_hint(),
                        session_language=_hint(),
                    )
                )
            if not chunk:
                any_empty_tool = True
                chunk = (
                    WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_PREFIX
                    + WORKFLOW_DESIGNER_TOOL_EMPTY_RESULT_LINE
                    + WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_SUFFIX.format(
                        language=_hint(),
                        session_language=_hint(),
                    )
                )
            context_chunks.append(chunk)

        if po.get("grep"):
            ctx.set_inline_status("Grep result…")
            grep_out = response.get("grep_output")
            text = ""
            if isinstance(grep_out, dict):
                text = (grep_out.get("out") or grep_out.get("data") or "").strip()
                err = grep_out.get("error")
                if isinstance(err, str) and err.strip():
                    text = f"{text}\nError: {err}".strip() if text else f"Error: {err}"
            elif grep_out is not None:
                text = str(grep_out).strip()
            body = text if text else WORKFLOW_DESIGNER_TOOL_EMPTY_RESULT_LINE
            if not text:
                any_empty_tool = True
            context_chunks.append(
                WORKFLOW_DESIGNER_GREP_FOLLOW_UP_PREFIX
                + body
                + WORKFLOW_DESIGNER_GREP_FOLLOW_UP_SUFFIX.format(
                    language=_hint(),
                    session_language=_hint(),
                )
            )

        if po.get("read_file"):
            ctx.set_inline_status("Reading file…")
            parts = []
            for path in po.get("read_file") or []:
                c = await asyncio.to_thread(
                    get_rag_context_by_path,
                    path,
                    "Workflow Designer",
                )
                if c and c.strip():
                    parts.append(f"--- {path} ---\n{c.strip()}")
            if parts:
                context_chunks.append(
                    WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX
                    + "\n\n".join(parts)
                    + WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX.format(
                        language=_hint(),
                        session_language=_hint(),
                    )
                )
            else:
                any_empty_tool = True
                context_chunks.append(
                    WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX
                    + WORKFLOW_DESIGNER_TOOL_EMPTY_RESULT_LINE
                    + WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX.format(
                        language=_hint(),
                        session_language=_hint(),
                    )
                )

        if po.get("rag_search"):
            ctx.set_inline_status("Searching knowledge base…")
            rag_ctx = await asyncio.to_thread(
                get_rag_context,
                po["rag_search"],
                "Workflow Designer",
                po.get("rag_search_max_results"),
                po.get("rag_search_max_chars"),
                po.get("rag_search_snippet_max"),
            )
            rag_text = (
                rag_ctx.strip()
                if isinstance(rag_ctx, str)
                else str(rag_ctx or "").strip()
            )
            if not rag_text:
                rag_text = "(No relevant RAG context returned.)"
            context_chunks.append(
                WORKFLOW_DESIGNER_RAG_FOLLOW_UP_PREFIX
                + rag_text
                + WORKFLOW_DESIGNER_RAG_FOLLOW_UP_SUFFIX.format(
                    language=_hint(),
                    session_language=_hint(),
                )
            )

        if po.get("web_search"):
            ctx.set_inline_status("Searching web…")
            chunk_ws: str | None = None
            try:
                register_web_units()
                out, errs = run_workflow_with_errors(
                    WEB_SEARCH_WORKFLOW_PATH,
                    initial_inputs={"inject_query": {"data": po["web_search"]}},
                    unit_param_overrides={"web_search": {"max_results": po.get("web_search_max_results", 10)}},
                    format="dict",
                )
                if errs and ctx.is_current_run(ctx.token):
                    await ctx.toast(f"Web search error: {errs[0][1][:120]}")
                res = (out.get("web_search") or {}).get("out") or ""
                if res.strip():
                    chunk_ws = (
                        WORKFLOW_DESIGNER_WEB_SEARCH_FOLLOW_UP_PREFIX
                        + res
                        + WORKFLOW_DESIGNER_WEB_SEARCH_FOLLOW_UP_SUFFIX.format(
                            language=_hint(),
                            session_language=_hint(),
                        )
                    )
            except Exception:
                pass
            if not chunk_ws:
                any_empty_tool = True
                chunk_ws = (
                    WORKFLOW_DESIGNER_WEB_SEARCH_FOLLOW_UP_PREFIX
                    + WORKFLOW_DESIGNER_TOOL_EMPTY_RESULT_LINE
                    + WORKFLOW_DESIGNER_WEB_SEARCH_FOLLOW_UP_SUFFIX.format(
                        language=_hint(),
                        session_language=_hint(),
                    )
                )
            context_chunks.append(chunk_ws)

        if po.get("browse_url"):
            ctx.set_inline_status("Loading page…")
            chunk_br: str | None = None
            try:
                register_web_units()
                out, errs = run_workflow_with_errors(
                    BROWSER_WORKFLOW_PATH,
                    initial_inputs={"inject_url": {"data": po["browse_url"]}},
                    format="dict",
                )
                if errs and ctx.is_current_run(ctx.token):
                    await ctx.toast(f"Browse error: {errs[0][1][:120]}")
                res = (out.get("beautifulsoup") or {}).get("out") or ""
                if res.strip():
                    chunk_br = (
                        WORKFLOW_DESIGNER_BROWSE_FOLLOW_UP_PREFIX
                        + res
                        + WORKFLOW_DESIGNER_BROWSE_FOLLOW_UP_SUFFIX.format(
                            language=_hint(),
                            session_language=_hint(),
                        )
                    )
            except Exception:
                pass
            if not chunk_br:
                any_empty_tool = True
                chunk_br = (
                    WORKFLOW_DESIGNER_BROWSE_FOLLOW_UP_PREFIX
                    + WORKFLOW_DESIGNER_TOOL_EMPTY_RESULT_LINE
                    + WORKFLOW_DESIGNER_BROWSE_FOLLOW_UP_SUFFIX.format(
                        language=_hint(),
                        session_language=_hint(),
                    )
                )
            context_chunks.append(chunk_br)

        if po.get("github"):
            ctx.set_inline_status("Querying GitHub…")
            chunk_gh: str | None = None
            try:
                out, errs = run_workflow_with_errors(
                    GITHUB_GET_WORKFLOW_PATH,
                    initial_inputs={"inject_action": {"data": po["github"]}},
                    format="dict",
                )
                if errs and ctx.is_current_run(ctx.token):
                    await ctx.toast(f"GitHub error: {errs[0][1][:120]}")
                gh_out = out.get("github_get") or {}
                data = gh_out.get("data")
                err_msg = gh_out.get("error")
                if err_msg:
                    res = f"Error: {err_msg}"
                elif data is not None:
                    try:
                        res = json.dumps(data, indent=2, ensure_ascii=False)
                    except Exception:
                        res = str(data)
                    if len(res) > 8000:
                        res = res[:8000] + "\n... (truncated)"
                else:
                    res = ""
                if res.strip():
                    chunk_gh = (
                        WORKFLOW_DESIGNER_GITHUB_FOLLOW_UP_PREFIX
                        + res
                        + WORKFLOW_DESIGNER_GITHUB_FOLLOW_UP_SUFFIX.format(
                            language=_hint(),
                            session_language=_hint(),
                        )
                    )
            except Exception:
                pass
            if not chunk_gh:
                any_empty_tool = True
                chunk_gh = (
                    WORKFLOW_DESIGNER_GITHUB_FOLLOW_UP_PREFIX
                    + WORKFLOW_DESIGNER_TOOL_EMPTY_RESULT_LINE
                    + WORKFLOW_DESIGNER_GITHUB_FOLLOW_UP_SUFFIX.format(
                        language=_hint(),
                        session_language=_hint(),
                    )
                )
            context_chunks.append(chunk_gh)

        if po.get("report"):
            ctx.set_inline_status("Report…")
            ro = response.get("report_output") or {}
            lines: list[str] = []
            if isinstance(ro, dict):
                if ro.get("ok"):
                    pth = (ro.get("output_path") or "").strip()
                    lines.append(
                        "Report written successfully"
                        + (f" to {pth}" if pth else "")
                        + "."
                    )
                    prev = (ro.get("report_preview") or "").strip()
                    if prev:
                        lines.append("Preview:\n" + prev)
                else:
                    err = (ro.get("error") or "").strip() or "unknown error"
                    lines.append(f"Report failed: {err}")
            else:
                lines.append("Report action was processed.")
            body = "\n\n".join(lines)
            context_chunks.append(
                "IMPORTANT: Report result from your previous turn.\n\n"
                + body
                + WORKFLOW_DESIGNER_RAG_FOLLOW_UP_SUFFIX.format(
                    language=_hint(),
                    session_language=_hint(),
                )
            )

        follow_up_context: str | None = None
        if context_chunks:
            follow_up_context = "\n\n---\n\n".join(context_chunks)
        if read_code_ids_for_msg:
            follow_up_msg = WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_USER_MESSAGE.format(
                unit_ids=", ".join(str(x) for x in read_code_ids_for_msg),
                language=_hint(),
                session_language=_hint(),
            )
        elif any_empty_tool:
            follow_up_msg = WORKFLOW_DESIGNER_TOOL_EMPTY_USER_MESSAGE.format(
                language=_hint(),
                session_language=_hint(),
            )

        if not follow_up_context:
            break
        ctx.follow_up_contexts.append(follow_up_context)
        if not ctx.is_current_run(ctx.token):
            return None
        prev_reply = response.get("reply")
        prev_content = (
            prev_reply.get("action")
            if isinstance(prev_reply, dict) and "action" in prev_reply
            else (prev_reply if isinstance(prev_reply, str) else str(prev_reply or ""))
        )
        prev_content = (prev_content or "").strip()
        if prev_content:
            ctx.append_message(
                "assistant",
                prev_content,
                meta={
                    "turn_id": ctx.turn_id,
                    "assistant": ctx.assistant_label,
                    "source": "assistant_response",
                    "workflow_response": {"reply": prev_content},
                },
            )
        ctx.prepare_stream_row()
        follow_up_msg = ctx.normalize_user_message_for_workflow(follow_up_msg)
        _graph = ctx.graph_ref[0]
        _runtime = ctx.get_runtime_for_prompts(_graph)
        initial_inputs = build_assistant_workflow_initial_inputs(
            follow_up_msg,
            _graph,
            ctx.last_apply_result_ref[0],
            ctx.get_recent_changes() if ctx.get_recent_changes else None,
            follow_up_context,
            runtime=_runtime,
            coding_is_allowed=get_coding_is_allowed(),
            previous_turn=ctx.format_previous_turn(ctx.state.history),
            language_hint=_hint(),
            session_language=ctx.state.session_language,
        )
        _gd = _graph.model_dump(by_alias=True) if hasattr(_graph, "model_dump") else (_graph if isinstance(_graph, dict) else None)
        follow_up_overrides = {
            **ctx.overrides,
            "graph_summary": get_summary_params(get_coding_is_allowed(), _gd),
            "rag_search": {**(ctx.overrides.get("rag_search") or {}), "ignore": True},
        }
        response = await ctx.run_workflow_streaming(
            run_assistant_workflow,
            initial_inputs,
            follow_up_overrides,
            None,
        )
        maybe_pin_session_language_from_workflow_response(ctx.state, response)
        ctx.wf_language_hint[0] = default_wf_language_hint(ctx.state.session_language)
        if workflow_response_is_question(response):
            # Assistant asked the user a question in this round; stop chained follow-ups.
            break
        _capture_apply_failure(response)
        if not ctx.is_current_run(ctx.token):
            return None
    if preserved_apply_failure is not None:
        final_r = response.get("result") or {}
        if final_r.get("kind") != "applied":
            response = merge_preserved_apply_failure_into_response(response, preserved_apply_failure)
    return response


@dataclass
class PostApplyFollowUpContext:
    graph_ref: list[Any]
    state: Any
    token: Any
    turn_id: str
    assistant_label: str
    max_rounds: int
    wf_language_hint: list[str]
    is_current_run: Callable[[Any], bool]
    toast: Callable[[str], Awaitable[None]]
    set_inline_status: Callable[[str | None], None]
    append_message: Callable[..., None]
    prepare_stream_row: Callable[[], None]
    normalize_user_message_for_workflow: Callable[[str], str]
    last_apply_result_ref: list[Any]
    get_recent_changes: Callable[[], str | None] | None
    overrides: dict[str, Any]
    run_workflow_streaming: Callable[..., Awaitable[Any]]
    get_runtime_for_prompts: Callable[[Any], str]
    format_previous_turn: Callable[[list[Any]], str]
    replace_assistant_message_row: Callable[[dict[str, Any]], None]
    stream_buffer_ref: list[str]
    apply_fn: Callable[[Any], None]


@dataclass
class PostApplyFlags:
    had_import_workflow: bool
    had_todo: bool
    had_add_comment: bool


async def run_post_apply_follow_up_rounds(
    ctx: PostApplyFollowUpContext,
    *,
    result: dict[str, Any],
    content_holder: list[str],
    parser_chain_runner: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]],
    flags: PostApplyFlags,
) -> None:
    """After a successful canvas apply, run optional review assistant rounds (import / todo / …)."""
    from gui.flet.chat_with_the_assistants.todo_list_manager import graph_has_any_open_tasks

    def _hint() -> str:
        return ctx.wf_language_hint[0]

    def _post_apply_messages(round_idx: int) -> tuple[str, str] | None:
        if round_idx == 0:
            if flags.had_import_workflow:
                return (
                    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP.format(
                        language=_hint(),
                        session_language=_hint(),
                    ),
                    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP_USER_MESSAGE.format(
                        language=_hint(),
                        session_language=_hint(),
                    ),
                )
            if flags.had_add_comment and flags.had_todo:
                return (
                    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP.format(
                        language=_hint(),
                        session_language=_hint(),
                    ),
                    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP_USER_MESSAGE.format(
                        language=_hint(),
                        session_language=_hint(),
                    ),
                )
            if flags.had_add_comment:
                return (
                    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP.format(
                        language=_hint(),
                        session_language=_hint(),
                    ),
                    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP_USER_MESSAGE.format(
                        language=_hint(),
                        session_language=_hint(),
                    ),
                )
            if flags.had_todo:
                return (
                    WORKFLOW_DESIGNER_TODO_FOLLOW_UP.format(
                        language=_hint(),
                        session_language=_hint(),
                    ),
                    WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE.format(
                        language=_hint(),
                        session_language=_hint(),
                    ),
                )
            return (
                WORKFLOW_DESIGNER_DEFAULT_POST_APPLY_FOLLOW_UP.format(
                    language=_hint(),
                    session_language=_hint(),
                ),
                WORKFLOW_DESIGNER_DEFAULT_POST_APPLY_FOLLOW_UP_USER_MESSAGE.format(
                    language=_hint(),
                    session_language=_hint(),
                ),
            )
        if not graph_has_any_open_tasks(ctx.graph_ref[0]):
            return None
        return (
            WORKFLOW_DESIGNER_TODO_FOLLOW_UP.format(
                language=_hint(),
                session_language=_hint(),
            ),
            WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE.format(
                language=_hint(),
                session_language=_hint(),
            ),
        )

    content = content_holder[0]
    for post_round in range(ctx.max_rounds):
        pair = _post_apply_messages(post_round)
        if pair is None:
            break
        post_msg, post_user_msg = pair
        if not ctx.is_current_run(ctx.token):
            break
        ctx.set_inline_status("Reviewing…")
        try:
            ctx.prepare_stream_row()
            post_user_msg = ctx.normalize_user_message_for_workflow(post_user_msg)
            _graph = ctx.graph_ref[0]
            _gd_post = (
                _graph.model_dump(by_alias=True)
                if _graph is not None and hasattr(_graph, "model_dump")
                else (_graph if isinstance(_graph, dict) else None)
            )
            if isinstance(_gd_post, dict):
                ctx.overrides["graph_summary"] = get_summary_params(
                    get_coding_is_allowed(), _gd_post
                )
            _runtime = ctx.get_runtime_for_prompts(_graph)
            post_inputs = build_assistant_workflow_initial_inputs(
                post_user_msg,
                _graph,
                ctx.last_apply_result_ref[0],
                ctx.get_recent_changes() if ctx.get_recent_changes else None,
                post_msg,
                runtime=_runtime,
                coding_is_allowed=get_coding_is_allowed(),
                previous_turn=ctx.format_previous_turn(ctx.state.history),
                language_hint=_hint(),
                session_language=ctx.state.session_language,
            )
            post_response = await ctx.run_workflow_streaming(
                run_assistant_workflow,
                post_inputs,
                ctx.overrides,
                None,
            )
            post_chained = await parser_chain_runner(post_response)
            if post_chained is None:
                return
            post_response = post_chained
            post_raw = post_response.get("reply")
            if isinstance(post_raw, dict) and "action" in post_raw:
                post_raw = post_raw.get("action") or ""
            post_reply = (
                (post_raw if isinstance(post_raw, str) else str(post_raw or "")).strip()
            )
            if not post_reply and ctx.stream_buffer_ref[0]:
                post_reply = (ctx.stream_buffer_ref[0] or "").strip()
            if post_reply:
                content = content + "\n\n" + post_reply
                content_holder[0] = content
                result["content_for_display"] = content
                last = ctx.state.history[-1] if ctx.state.history else None
                if (
                    isinstance(last, dict)
                    and last.get("role") == "assistant"
                    and last.get("turn_id") == ctx.turn_id
                ):
                    last["content"] = content
                    wr = last.get("workflow_response")
                    if isinstance(wr, dict):
                        wr["reply"] = content
                    else:
                        last["workflow_response"] = {"reply": content}
                    ctx.replace_assistant_message_row(last)
                else:
                    ctx.append_message(
                        "assistant",
                        post_reply,
                        meta={
                            "turn_id": ctx.turn_id,
                            "assistant": ctx.assistant_label,
                            "source": "assistant_response_post_apply",
                            "workflow_response": {
                                "reply": post_reply,
                                "result_kind": "post_apply",
                                "post_apply_round": post_round,
                            },
                        },
                    )
            if workflow_response_is_question(post_response):
                # Assistant asked the user a question; stop post-apply auto rounds.
                break
            pw = post_response.get("result") or {}
            post_kind = pw.get("kind")
            post_graph = pw.get("graph")
            synced_post_graph = False
            if (
                post_kind == "applied"
                and post_graph is not None
                and ctx.is_current_run(ctx.token)
            ):
                try:
                    if isinstance(post_graph, dict):
                        from gui.flet.chat_with_the_assistants.todo_list_manager import (
                            augment_graph_with_client_tasks,
                        )

                        post_graph, _post_supp = augment_graph_with_client_tasks(
                            post_graph,
                            pw.get("edits") or [],
                            coding_is_allowed=get_coding_is_allowed(),
                        )
                        post_pg, _p_err = validate_graph_to_apply_for_canvas(post_graph)
                    else:
                        post_pg = post_graph
                    if post_pg is not None:
                        ctx.apply_fn(post_pg)
                        ctx.last_apply_result_ref[0] = refresh_last_apply_result_after_canvas_apply(
                            ctx.last_apply_result_ref[0],
                            ctx.graph_ref[0],
                            supplement_summary="",
                        )
                        synced_post_graph = True
                except Exception:
                    pass
            if not synced_post_graph and pw.get("last_apply_result"):
                ctx.last_apply_result_ref[0] = pw["last_apply_result"]
            post_errors = post_response.get("workflow_errors") or []
            if post_errors and ctx.is_current_run(ctx.token):
                await ctx.toast(f"Workflow error: {post_errors[0][1][:120]}")
        except Exception:
            pass
        ctx.set_inline_status(None)
