"""
Workflow Designer: parser-output tool follow-up chain and post-apply review rounds.

Orchestrates Workflow Designer tool follow-ups in catalog order (registered tool runners),
then re-runs assistant_workflow; optional post-apply rounds (import/todo/comment).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import flet as ft

from assistants.prompts import (
    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP,
    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP,
    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_DEFAULT_POST_APPLY_FOLLOW_UP,
    WORKFLOW_DESIGNER_DEFAULT_POST_APPLY_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP,
    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_TODO_FOLLOW_UP,
    WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE,
)
from assistants.tools.follow_up_common import TOOL_EMPTY_USER_MESSAGE
from assistants.tools.read_code_block.follow_ups import READ_CODE_BLOCK_FOLLOW_UP_USER_MESSAGE
from gui.flet.chat_with_the_assistants.language_control import maybe_pin_session_language_from_workflow_response
from gui.flet.chat_with_the_assistants.todo_list_manager import get_summary_params
from assistants.roles.workflow_designer.workflow_inputs import (
    build_assistant_workflow_initial_inputs,
    default_wf_language_hint,
)
from gui.flet.chat_with_the_assistants.workflow_designer_handler import (
    run_assistant_workflow,
    refresh_last_apply_result_after_canvas_apply,
)
from gui.flet.components.settings import get_coding_is_allowed
from gui.flet.components.workflow.core_workflows import validate_graph_to_apply_for_canvas
from gui.flet.utils.workflow_output_normalizer import normalize_follow_up_parser_output

from assistants.tools.catalog import ORDERED_WORKFLOW_DESIGNER_TOOLS
from assistants.tools.registry import get_follow_up_runner
from assistants.tools.types import (
    FOLLOW_UP_EXTRA_IMPLEMENTATION_LINK_TYPES,
    FOLLOW_UP_EXTRA_READ_CODE_IDS,
    FollowUpContribution,
)


def _follow_up_tool_enabled(ctx: "ParserFollowUpContext", tool_id: str) -> bool:
    """If ``follow_up_tool_ids`` is set, only listed tools run; empty tuple disables all tools."""
    allowed = ctx.follow_up_tool_ids
    if allowed is None:
        return True
    return tool_id in allowed


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
    # None = all Workflow Designer follow-up tools; else allowlist (tool ids from catalog / role.yaml)
    follow_up_tool_ids: tuple[str, ...] | None = None
    # Workflow response dict for the current follow-up round (grep_output, run_output, …).
    follow_up_source_response: dict[str, Any] | None = None
    # ``assistants.roles`` id (e.g. ``workflow_designer``); used for RAG follow-ups, not only UI label.
    assistant_role_id: str | None = None


@dataclass
class WDFollowUpAcc:
    """Mutable accumulators for one parser follow-up round (ordered tool loop)."""

    context_chunks: list[str] = field(default_factory=list)
    any_empty_tool: bool = False
    read_code_ids_for_msg: list[str] = field(default_factory=list)
    implementation_links_for_types: list[str] = field(default_factory=list)


def _merge_follow_up_contribution_into_acc(acc: WDFollowUpAcc, contrib: FollowUpContribution) -> None:
    acc.context_chunks.extend(contrib.context_chunks)
    if contrib.any_empty_tool:
        acc.any_empty_tool = True
    ex = contrib.extra
    if FOLLOW_UP_EXTRA_READ_CODE_IDS in ex:
        v = ex[FOLLOW_UP_EXTRA_READ_CODE_IDS]
        if isinstance(v, list):
            acc.read_code_ids_for_msg = [str(x) for x in v]
    if FOLLOW_UP_EXTRA_IMPLEMENTATION_LINK_TYPES in ex:
        v = ex[FOLLOW_UP_EXTRA_IMPLEMENTATION_LINK_TYPES]
        if isinstance(v, list):
            acc.implementation_links_for_types = [str(x) for x in v]


async def _run_workflow_designer_ordered_follow_ups(
    ctx: ParserFollowUpContext,
    po: dict[str, Any],
    response: dict[str, Any],
    hint: Callable[[], str],
    acc: WDFollowUpAcc,
) -> None:
    """Run follow-ups in catalog order via registered tool runners."""
    for tool_id, parser_key in ORDERED_WORKFLOW_DESIGNER_TOOLS:
        if not _follow_up_tool_enabled(ctx, tool_id):
            continue
        if not po.get(parser_key):
            continue
        runner = get_follow_up_runner(tool_id)
        if not callable(runner):
            continue
        try:
            contrib = await runner(ctx, po, language_hint=hint)
        except Exception:
            contrib = None
        if contrib is not None:
            _merge_follow_up_contribution_into_acc(acc, contrib)


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
        follow_up_msg = WORKFLOW_DESIGNER_FOLLOW_UP_USER_MESSAGE.format(
            language=_hint(),
            session_language=_hint(),
        )
        acc = WDFollowUpAcc()
        ctx.follow_up_source_response = response
        await _run_workflow_designer_ordered_follow_ups(ctx, po, response, _hint, acc)
        context_chunks = acc.context_chunks
        any_empty_tool = acc.any_empty_tool
        read_code_ids_for_msg = acc.read_code_ids_for_msg
        implementation_links_for_types = acc.implementation_links_for_types

        follow_up_context: str | None = None
        if context_chunks:
            follow_up_context = "\n\n---\n\n".join(context_chunks)
        if read_code_ids_for_msg:
            follow_up_msg = READ_CODE_BLOCK_FOLLOW_UP_USER_MESSAGE.format(
                unit_ids=", ".join(str(x) for x in read_code_ids_for_msg),
                language=_hint(),
                session_language=_hint(),
            )
        elif any_empty_tool:
            follow_up_msg = TOOL_EMPTY_USER_MESSAGE.format(
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
        ul_base = dict(ctx.overrides.get("units_library") or {})
        if implementation_links_for_types:
            ul_merged = {
                **ul_base,
                "implementation_links_for_types": list(dict.fromkeys(implementation_links_for_types)),
            }
        else:
            ul_merged = {k: v for k, v in ul_base.items() if k != "implementation_links_for_types"}
        follow_up_overrides = {
            **ctx.overrides,
            "graph_summary": get_summary_params(get_coding_is_allowed(), _gd),
            "rag_search": {**(ctx.overrides.get("rag_search") or {}), "ignore": True},
            "units_library": ul_merged,
        }
        response = await ctx.run_workflow_streaming(
            run_assistant_workflow,
            initial_inputs,
            follow_up_overrides,
            None,
            _run_token=ctx.token,
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
    assistant_role_id: str
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
                _run_token=ctx.token,
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
                        from gui.flet.chat_with_the_assistants.role_handlers.turn_edits import (
                            canonicalize_add_comment_edits,
                        )
                        from gui.flet.chat_with_the_assistants.todo_list_manager import (
                            augment_graph_with_client_tasks,
                        )

                        _post_edits = pw.get("edits") or []
                        canonicalize_add_comment_edits(_post_edits, assistant_role_id=ctx.assistant_role_id)
                        post_graph, _post_supp = augment_graph_with_client_tasks(
                            post_graph,
                            _post_edits,
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
