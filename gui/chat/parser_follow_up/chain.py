"""
Parser-output tool follow-up chain and post-apply review rounds for agents chat.

Orchestrates tool follow-ups in catalog order (registered tool runners), then re-runs
``agent_workflow``; optional post-apply rounds (import / todo / comment).
"""

from __future__ import annotations

import asyncio
import inspect
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, cast

if TYPE_CHECKING:
    import flet as ft

import agents.follow_ups as agents_follow_ups
from agents.prompts import (
    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP,
    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP,
    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP,
    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP_USER_MESSAGE,
    WORKFLOW_DESIGNER_TODO_FOLLOW_UP,
    WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE,
)
from agents.roles.workflow_designer.workflow_inputs import (
    build_agent_workflow_initial_inputs,
    default_wf_language_hint,
)
from agents.tools.catalog import ORDERED_WORKFLOW_DESIGNER_TOOLS
from agents.tools.follow_up_common import TOOL_EMPTY_USER_MESSAGE
from agents.tools.formulas_calc.follow_ups import (
    FORMULAS_CALC_FOLLOW_UP_USER_MESSAGE,
)
from agents.tools.read_code_block.follow_ups import (
    READ_CODE_BLOCK_FOLLOW_UP_USER_MESSAGE,
)
from agents.tools.registry import get_follow_up_runner
from agents.tools.report.follow_ups import REPORT_FOLLOW_UP_USER_MESSAGE
from agents.tools.types import (
    FOLLOW_UP_EXTRA_FORMULAS_CALC_FOLLOW_UP,
    FOLLOW_UP_EXTRA_IMPLEMENTATION_LINK_TYPES,
    FOLLOW_UP_EXTRA_READ_CODE_IDS,
    FOLLOW_UP_EXTRA_REPORT_FOLLOW_UP,
    FollowUpContribution,
)
from gui.chat.agent_workflow import (
    refresh_last_apply_result_after_canvas_apply,
    run_agent_workflow,
)
from gui.chat.context.language_control import (
    maybe_pin_session_language_from_workflow_response,
)
from gui.chat.context.llm_prompt_inspector import record_llm_prompt_view_if_present
from gui.chat.context.todo_list_manager import get_summary_params
from gui.components.settings import get_coding_is_allowed, get_contribution_is_allowed
from gui.components.workflow_tab.workflows.core_workflows import (
    validate_graph_to_apply_for_canvas,
)
from gui.utils.workflow_output_normalizer import (
    formulas_calc_display_appendix,
    normalize_follow_up_parser_output,
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
    if (
        isinstance(st, dict)
        and st.get("attempted") is True
        and st.get("success") is False
    ):
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
    """True when agent workflow classified the current reply as a user question."""
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

    page: "ft.Page | None"  # quoted forward ref so runtime doesn't need ft
    graph_ref: list[Any]
    state: Any
    token: Any
    turn_id: str
    agent_label: str
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
    get_runtime_for_prompts: Callable[[Any], Awaitable[Literal["native", "external"]]]
    format_previous_turn: Callable[[list[dict[str, Any]]], Awaitable[str]]
    on_show_run_console: Callable[..., None] | None = None
    # None = all Workflow Designer follow-up tools; else allowlist (tool ids from catalog / role.yaml)
    follow_up_tool_ids: tuple[str, ...] | None = None
    # Workflow response dict for the current follow-up round (grep_output, run_output, …).
    follow_up_source_response: dict[str, Any] | None = None
    # ``agents.roles`` id (e.g. ``workflow_designer``); used for RAG follow-ups, not only UI label.
    agent_role_id: str | None = None
    # When set, ``run_agent_workflow`` uses this JSON instead of the Workflow Designer default.
    agent_workflow_path: Path | None = None
    # Analyst chat: slimmer injects + hidden graph structure in summary overrides.
    analyst_mode: bool = False
    # When set, only these (tool_id, parser_key) pairs run in follow-up order; else WD catalog order.
    ordered_follow_up_tools: tuple[tuple[str, str], ...] | None = None
    # Dev: optional callback with response dict (llm_system_prompt / llm_user_message).
    record_llm_prompt_view: Callable[[dict[str, Any]], None] | None = None
    # RL Coach (and similar): merge training injects after ``build_agent_workflow_initial_inputs``.
    extend_agent_initial_inputs_async: (
        Callable[[dict[str, dict[str, Any]]], Awaitable[dict[str, dict[str, Any]]]]
        | None
    ) = None


@dataclass
class WDFollowUpAcc:
    """Mutable accumulators for one parser follow-up round (ordered tool loop)."""

    context_chunks: list[str] = field(default_factory=list)
    any_empty_tool: bool = False
    read_code_ids_for_msg: list[str] = field(default_factory=list)
    implementation_links_for_types: list[str] = field(default_factory=list)
    report_follow_up: bool = False
    formulas_calc_follow_up: bool = False


def _merge_follow_up_contribution_into_acc(
    acc: WDFollowUpAcc, contrib: FollowUpContribution
) -> None:
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
    if ex.get(FOLLOW_UP_EXTRA_REPORT_FOLLOW_UP):
        acc.report_follow_up = True
    if ex.get(FOLLOW_UP_EXTRA_FORMULAS_CALC_FOLLOW_UP):
        acc.formulas_calc_follow_up = True


async def _run_workflow_designer_ordered_follow_ups(
    ctx: "ParserFollowUpContext",
    po: dict[str, Any],
    response: dict[str, Any],
    hint: Callable[[], str],
    acc: "WDFollowUpAcc",
) -> None:
    ordered = (
        getattr(ctx, "ordered_follow_up_tools", None) or ORDERED_WORKFLOW_DESIGNER_TOOLS
    )

    for tool_id, parser_key in ordered:
        if not _follow_up_tool_enabled(ctx, tool_id):
            continue

        print(
            f"[parser_follow_up_chain] followup_tool_enabled tool_id={tool_id}",
            flush=True,
        )

        if not po.get(parser_key):
            continue

        val = po.get(parser_key)
        print(
            f"[parser_follow_up_chain] gate parser_key={parser_key} val={type(val).__name__} truth={bool(val)} repr={repr(val)[:200]}",
            flush=True,
        )

        runner = get_follow_up_runner(tool_id)
        if not callable(runner):
            continue

        print(
            f"[parser_follow_up_chain] followup_runner_start tool_id={tool_id} parser_key={parser_key}",
            flush=True,
        )

        result = runner(ctx, po, language_hint=hint)

        try:
            if inspect.isawaitable(result):
                print(
                    f"[parser_follow_up_chain] waiting tool_id={tool_id} parser_key={parser_key}",
                    flush=True,
                )
                contrib = await result
            else:
                contrib = result
        except Exception as e:
            print(
                f"[parser_follow_up_chain] followup_runner_await_failed tool_id={tool_id} parser_key={parser_key}: {type(e).__name__}: {e}",
                flush=True,
            )
            traceback.print_exc()
            raise

        if contrib is not None:
            _merge_follow_up_contribution_into_acc(
                acc, cast("FollowUpContribution", contrib)
            )


# ─────────────────────────────────────────────────────────────────────────────────
#  Parser follow-up chain
# ─────────────────────────────────────────────────────────────────────────────────


async def run_parser_output_follow_up_chain_async(
    ctx: ParserFollowUpContext,
    resp: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Async version: If parser_output requests tools, fetch context and re-run agent_workflow.
    Returns None when the user cancelled the run mid-chain.
    """

    def _hint() -> str:
        return ctx.wf_language_hint[0]

    async def _checkpoint(name: str) -> None:
        print(f"[parser_follow_up_chain] checkpoint: {name} ts={time.time():.3f}")

    maybe_pin_session_language_from_workflow_response(ctx.state, resp)
    ctx.wf_language_hint[0] = default_wf_language_hint(ctx.state.session_language)
    preserved_apply_failure: dict[str, Any] = {}
    preserved_apply_failure_set = False

    def _capture_apply_failure(r: dict[str, Any]) -> None:
        nonlocal preserved_apply_failure, preserved_apply_failure_set
        if not workflow_merge_response_apply_failed(r):
            return
        preserved_apply_failure = {
            "result": dict(r.get("result") or {}),
            "status": dict(r.get("status") or {})
            if isinstance(r.get("status"), dict)
            else r.get("status"),
            "workflow_errors": list(r.get("workflow_errors") or []),
        }
        preserved_apply_failure_set = True

    response = resp
    if asyncio.iscoroutine(response):
        response = await response
    if not isinstance(response, dict):
        raise TypeError(
            f"run_parser_output_follow_up_chain_async got {type(response).__name__}, expected dict"
        )

    record_llm_prompt_view_if_present(resp, ctx.record_llm_prompt_view)
    _capture_apply_failure(resp)
    await _checkpoint("after_primer")

    if workflow_response_is_question(response):
        await _checkpoint("return_question_no_chain")
        return response

    for i in range(ctx.max_rounds):
        await _checkpoint(f"loop_start:{i}")

        po = normalize_follow_up_parser_output(response.get("parser_output"))
        print(
            "[parser_follow_up_chain] po type="
            + type(po).__name__
            + " keys="
            + (str(list(po.keys())) if isinstance(po, dict) else "None"),
            flush=True,
        )
        print("[parser_follow_up_chain] po=" + repr(po), flush=True)
        follow_up_msg = WORKFLOW_DESIGNER_FOLLOW_UP_USER_MESSAGE.format(
            language=_hint(),
            session_language=_hint(),
        )
        acc = WDFollowUpAcc()
        ctx.follow_up_source_response = response

        await _checkpoint(f"before_ordered_followups:{i}")
        await _run_workflow_designer_ordered_follow_ups(ctx, po, response, _hint, acc)
        await _checkpoint(f"after_ordered_followups:{i}")

        context_chunks = acc.context_chunks
        any_empty_tool = acc.any_empty_tool
        read_code_ids_for_msg = acc.read_code_ids_for_msg
        implementation_links_for_types = acc.implementation_links_for_types
        report_follow_up = acc.report_follow_up
        formulas_calc_follow_up = acc.formulas_calc_follow_up

        follow_up_context: str | None = None
        if context_chunks:
            follow_up_context = "\n\n---\n\n".join(context_chunks)

        if read_code_ids_for_msg:
            follow_up_msg = READ_CODE_BLOCK_FOLLOW_UP_USER_MESSAGE.format(
                unit_ids=", ".join(str(x) for x in read_code_ids_for_msg),
                language=_hint(),
                session_language=_hint(),
            )
        elif report_follow_up:
            follow_up_msg = REPORT_FOLLOW_UP_USER_MESSAGE.format(
                language=_hint(),
                session_language=_hint(),
            )
        elif any_empty_tool:
            follow_up_msg = TOOL_EMPTY_USER_MESSAGE.format(
                language=_hint(),
                session_language=_hint(),
            )
        elif formulas_calc_follow_up:
            follow_up_msg = FORMULAS_CALC_FOLLOW_UP_USER_MESSAGE.format(
                language=_hint(),
                session_language=_hint(),
            )

        if not follow_up_context:
            await _checkpoint(f"break_no_follow_up_context:{i}")
            break

        ctx.follow_up_contexts.append(follow_up_context)
        await _checkpoint(f"appended_follow_up_context:{i}")

        if not ctx.is_current_run(ctx.token):
            await _checkpoint(f"return_none_cancelled_pre_llm:{i}")
            return None

        prev_reply = response.get("reply")
        prev_content = (
            prev_reply.get("action")
            if isinstance(prev_reply, dict) and "action" in prev_reply
            else (prev_reply if isinstance(prev_reply, str) else str(prev_reply or ""))
        )
        prev_content = (prev_content or "").strip()
        if prev_content:
            prev_show = prev_content + formulas_calc_display_appendix(response)
            ctx.append_message(
                "agent",
                prev_show,
                meta={
                    "turn_id": ctx.turn_id,
                    "agent": ctx.agent_label,
                    "source": "agent_response",
                    "workflow_response": {"reply": prev_show},
                },
            )

        ctx.prepare_stream_row()
        follow_up_msg = ctx.normalize_user_message_for_workflow(follow_up_msg)
        _graph = ctx.graph_ref[0]
        _runtime = await ctx.get_runtime_for_prompts(_graph)
        _previous_turn = await ctx.format_previous_turn(ctx.state.history)

        initial_inputs = build_agent_workflow_initial_inputs(
            follow_up_msg,
            _graph,
            ctx.last_apply_result_ref[0],
            ctx.get_recent_changes() if ctx.get_recent_changes else None,
            follow_up_context,
            runtime=_runtime,
            coding_is_allowed=get_coding_is_allowed(),
            contribution_is_allowed=get_contribution_is_allowed(),
            previous_turn=_previous_turn,
            language_hint=_hint(),
            session_language=ctx.state.session_language,
            analyst_mode=ctx.analyst_mode,
        )

        if ctx.extend_agent_initial_inputs_async is not None:
            await _checkpoint(f"before_extend_initial_inputs:{i}")
            initial_inputs = await ctx.extend_agent_initial_inputs_async(initial_inputs)
            await _checkpoint(f"after_extend_initial_inputs:{i}")

        _gd = (
            _graph.model_dump(by_alias=True)
            if hasattr(_graph, "model_dump")
            else (_graph if isinstance(_graph, dict) else None)
        )
        ul_base = dict(ctx.overrides.get("units_library") or {})

        if implementation_links_for_types:
            ul_merged = {
                **ul_base,
                "implementation_links_for_types": list(
                    dict.fromkeys(implementation_links_for_types)
                ),
            }
        else:
            ul_merged = {
                k: v
                for k, v in ul_base.items()
                if k != "implementation_links_for_types"
            }

        if ctx.analyst_mode:
            gs = dict(ctx.overrides.get("graph_summary") or {})
            gs.setdefault("include_structure", False)
            gs.setdefault("include_code_block_source", False)
        else:
            gs = get_summary_params(get_coding_is_allowed(), _gd)

        follow_up_overrides = {
            **ctx.overrides,
            "graph_summary": gs,
            "rag_search": {**(ctx.overrides.get("rag_search") or {}), "ignore": True},
            "units_library": ul_merged,
        }

        stream_kw: dict[str, Any] = {"_run_token": ctx.token}
        if ctx.agent_workflow_path is not None:
            stream_kw["workflow_path"] = ctx.agent_workflow_path

        await _checkpoint(f"before_run_workflow_streaming:{i}")

        async def _run_agent_workflow_async(*a: Any, **k: Any) -> Any:
            return await run_agent_workflow(*a, **k)

        response = await ctx.run_workflow_streaming(
            _run_agent_workflow_async,
            initial_inputs,
            follow_up_overrides,
            None,
            **stream_kw,
        )

        await _checkpoint(f"after_run_workflow_streaming:{i}")

        if asyncio.iscoroutine(response):
            response = await response
        if not isinstance(response, dict):
            raise TypeError(
                f"run_workflow_streaming returned {type(response).__name__}, expected dict"
            )

        record_llm_prompt_view_if_present(response, ctx.record_llm_prompt_view)
        maybe_pin_session_language_from_workflow_response(ctx.state, response)
        ctx.wf_language_hint[0] = default_wf_language_hint(ctx.state.session_language)

        if workflow_response_is_question(response):
            await _checkpoint(f"break_question_after_stream:{i}")
            break

        _capture_apply_failure(response)

        if not ctx.is_current_run(ctx.token):
            await _checkpoint(f"return_none_cancelled_post_llm:{i}")
            return None

        await _checkpoint(f"end_round_no_question:{i}")

    await _checkpoint("exit_after_rounds_or_break")

    if preserved_apply_failure_set:
        final_r = response.get("result") or {}
        if final_r.get("kind") != "applied":
            response = merge_preserved_apply_failure_into_response(
                response, preserved_apply_failure
            )

    await _checkpoint("return_final_response")
    return response


# ─────────────────────────────────────────────────────────────────────────────────
#  Post-apply follow-up rounds
# ─────────────────────────────────────────────────────────────────────────────────


@dataclass
class PostApplyFollowUpContext:
    graph_ref: list[Any]
    state: Any
    token: Any
    turn_id: str
    agent_role_id: str
    agent_label: str
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
    get_runtime_for_prompts: Callable[[Any], Awaitable[Literal["native", "external"]]]
    format_previous_turn: Callable[[list[dict[str, Any]]], Awaitable[str]]
    replace_agent_message_row: Callable[[dict[str, Any]], None]
    stream_buffer_ref: list[str]
    apply_fn: Callable[[Any], None]
    agent_workflow_path: Path | None = None
    analyst_mode: bool = False
    record_llm_prompt_view: Callable[[dict[str, Any]], None] | None = field(
        default=None, kw_only=True
    )


@dataclass
class PostApplyFlags:
    had_import_workflow: bool
    had_todo: bool
    had_add_comment: bool


# ─────────────────────────────────────────────────────────────────────────────────
#  Post-apply follow-up rounds (logged version)
# ─────────────────────────────────────────────────────────────────────────────────


async def run_post_apply_follow_up_rounds_async(
    ctx: PostApplyFollowUpContext,
    *,
    result: dict[str, Any],
    content_holder: list[str],
    parser_chain_runner: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]],
    flags: PostApplyFlags,
) -> None:
    """After a successful canvas apply, run optional review agent rounds (import / todo / …)."""
    from gui.chat.context.todo_list_manager import graph_has_any_open_tasks

    def _hint() -> str:
        return ctx.wf_language_hint[0]

    async def _checkpoint(name: str) -> None:
        print(
            f"[post_apply_follow_up_rounds] checkpoint: {name} ts={time.time():.3f}",
            flush=True,
        )

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
                agents_follow_ups.DEFAULT_POST_APPLY_FOLLOW_UP_INJECT.format(
                    language=_hint(),
                    session_language=_hint(),
                ),
                agents_follow_ups.DEFAULT_POST_APPLY_FOLLOW_UP_USER_MESSAGE.format(
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
    await _checkpoint("start")
    for post_round in range(ctx.max_rounds):
        await _checkpoint(f"loop_start:{post_round}")

        pair = _post_apply_messages(post_round)
        await _checkpoint(
            f"after_pick_messages:{post_round}:{'None' if pair is None else 'pair'}"
        )
        if pair is None:
            await _checkpoint(f"break_no_pair:{post_round}")
            break
        post_msg, post_user_msg = pair

        if not ctx.is_current_run(ctx.token):
            await _checkpoint(f"break_not_current_run:{post_round}")
            break

        ctx.set_inline_status("Reviewing…")
        await _checkpoint(f"set_inline_status:{post_round}")

        try:
            ctx.prepare_stream_row()
            await _checkpoint(f"prepared_stream_row:{post_round}")

            post_user_msg = ctx.normalize_user_message_for_workflow(post_user_msg)
            await _checkpoint(f"normalized_user_msg:{post_round}")

            _graph = ctx.graph_ref[0]
            await _checkpoint(f"read_graph_ref:{post_round}:{_graph is not None}")

            _gd_post = (
                _graph.model_dump(by_alias=True)
                if _graph is not None and hasattr(_graph, "model_dump")
                else (_graph if isinstance(_graph, dict) else None)
            )
            await _checkpoint(
                f"computed_graph_dump:{post_round}:{isinstance(_gd_post, dict)}"
            )

            if isinstance(_gd_post, dict):
                if ctx.analyst_mode:
                    gs = dict(ctx.overrides.get("graph_summary") or {})
                    gs.setdefault("include_structure", False)
                    gs.setdefault("include_code_block_source", False)
                    ctx.overrides["graph_summary"] = gs
                    await _checkpoint(f"analyst_mode_graph_summary_set:{post_round}")
                else:
                    ctx.overrides["graph_summary"] = get_summary_params(
                        get_coding_is_allowed(), _gd_post
                    )
                    await _checkpoint(f"graph_summary_set:{post_round}")

            _runtime = await ctx.get_runtime_for_prompts(_graph)
            await _checkpoint(
                f"runtime_for_prompts:{post_round}:{_runtime is not None}"
            )
            _previous_turn = await ctx.format_previous_turn(ctx.state.history)
            last_apply = ctx.last_apply_result_ref[0]

            if asyncio.iscoroutine(last_apply):
                last_apply = await last_apply

            post_inputs = build_agent_workflow_initial_inputs(
                post_user_msg,
                _graph,
                last_apply if isinstance(last_apply, dict) else None,
                ctx.get_recent_changes() if ctx.get_recent_changes else None,
                post_msg,
                runtime=_runtime,
                coding_is_allowed=get_coding_is_allowed(),
                contribution_is_allowed=get_contribution_is_allowed(),
                previous_turn=_previous_turn,
                language_hint=_hint(),
                session_language=ctx.state.session_language,
                analyst_mode=ctx.analyst_mode,
            )
            await _checkpoint(f"built_post_inputs:{post_round}")

            post_stream_kw: dict[str, Any] = {"_run_token": ctx.token}
            if ctx.agent_workflow_path is not None:
                post_stream_kw["workflow_path"] = ctx.agent_workflow_path
                await _checkpoint(f"using_agent_workflow_path:{post_round}")
            else:
                await _checkpoint(f"no_agent_workflow_path:{post_round}")

            await _checkpoint(f"before_run_workflow_streaming:{post_round}")
            post_response = await ctx.run_workflow_streaming(
                run_agent_workflow,
                post_inputs,
                ctx.overrides,
                None,
                **post_stream_kw,
            )
            await _checkpoint(f"after_run_workflow_streaming:{post_round}")

            await _checkpoint(f"before_parser_chain:{post_round}")
            post_chained = await parser_chain_runner(post_response)
            await _checkpoint(f"after_parser_chain:{post_round}:{post_chained is None}")

            if post_chained is None:
                await _checkpoint(f"return_none_from_parser_chain:{post_round}")
                return
            post_response = post_chained

            record_llm_prompt_view_if_present(post_response, ctx.record_llm_prompt_view)
            await _checkpoint(f"recorded_prompt_view:{post_round}")

            post_raw = post_response.get("reply")
            if isinstance(post_raw, dict) and "action" in post_raw:
                post_raw = post_raw.get("action") or ""
                await _checkpoint(f"extracted_action_from_reply:{post_round}")

            post_reply = (
                post_raw if isinstance(post_raw, str) else str(post_raw or "")
            ).strip()

            if not post_reply and ctx.stream_buffer_ref[0]:
                post_reply = (ctx.stream_buffer_ref[0] or "").strip()
                await _checkpoint(f"used_stream_buffer_fallback:{post_round}")

            await _checkpoint(f"computed_post_reply_len:{post_round}:{len(post_reply)}")

            if post_reply:
                content = content + "\n\n" + post_reply
                content_holder[0] = content
                result["content_for_display"] = content
                await _checkpoint(f"appended_post_reply:{post_round}:{len(content)}")

                last = ctx.state.history[-1] if ctx.state.history else None
                await _checkpoint(
                    f"history_last_present:{post_round}:{isinstance(last, dict)}"
                )

                if (
                    isinstance(last, dict)
                    and last.get("role") == "agent"
                    and last.get("turn_id") == ctx.turn_id
                ):
                    last["content"] = content
                    wr = last.get("workflow_response")
                    if isinstance(wr, dict):
                        wr["reply"] = content
                    else:
                        last["workflow_response"] = {"reply": content}
                    ctx.replace_agent_message_row(last)
                    await _checkpoint(f"replaced_agent_row:{post_round}")
                else:
                    ctx.append_message(
                        "agent",
                        post_reply,
                        meta={
                            "turn_id": ctx.turn_id,
                            "agent": ctx.agent_label,
                            "source": "agent_response_post_apply",
                            "workflow_response": {
                                "reply": post_reply,
                                "result_kind": "post_apply",
                                "post_apply_round": post_round,
                            },
                        },
                    )
                    await _checkpoint(f"appended_agent_message:{post_round}")

            await _checkpoint(f"before_workflow_response_question_check:{post_round}")
            if workflow_response_is_question(post_response):
                await _checkpoint(f"break_question_stop_auto_rounds:{post_round}")
                break

            pw = post_response.get("result") or {}
            post_kind = pw.get("kind")
            post_graph = pw.get("graph")
            await _checkpoint(
                f"post_result_fields:{post_round}:kind={post_kind}:{post_graph is not None}"
            )

            synced_post_graph = False
            if (
                post_kind == "applied"
                and post_graph is not None
                and ctx.is_current_run(ctx.token)
            ):
                await _checkpoint(f"attempt_canvas_sync:{post_round}")
                try:
                    if isinstance(post_graph, dict):
                        from gui.chat.context.todo_list_manager import (
                            augment_graph_with_client_tasks,
                        )
                        from gui.chat.role_turns.turn_edits import (
                            canonicalize_add_comment_edits,
                        )

                        _post_edits = pw.get("edits") or []
                        await _checkpoint(
                            f"canonicalize_add_comment_edits:{post_round}:{len(_post_edits)}"
                        )
                        await canonicalize_add_comment_edits(
                            _post_edits, agent_role_id=ctx.agent_role_id
                        )

                        post_graph, _post_supp = await asyncio.to_thread(
                            augment_graph_with_client_tasks,
                            post_graph,
                            _post_edits,
                            coding_is_allowed=get_coding_is_allowed(),
                        )
                        await _checkpoint(
                            f"augment_graph_with_client_tasks:{post_round}"
                        )
                        post_pg, _p_err = await validate_graph_to_apply_for_canvas(
                            post_graph
                        )
                        await _checkpoint(
                            f"validated_graph_to_apply_for_canvas:{post_round}:{post_pg is not None}"
                        )
                    else:
                        post_pg = post_graph
                        await _checkpoint(f"post_graph_not_dict:{post_round}")

                    if post_pg is not None:
                        ctx.apply_fn(post_pg)
                        await _checkpoint(f"applied_post_graph:{post_round}")

                        prev_apply = ctx.last_apply_result_ref[0]
                        if asyncio.iscoroutine(prev_apply):
                            prev_apply = await prev_apply

                        ctx.last_apply_result_ref[
                            0
                        ] = await refresh_last_apply_result_after_canvas_apply(
                            prev_apply,
                            ctx.graph_ref[0],
                            supplement_summary="",
                        )

                        synced_post_graph = True
                        await _checkpoint(f"refreshed_last_apply_result:{post_round}")
                    else:
                        await _checkpoint(f"post_pg_is_none_no_apply:{post_round}")
                except Exception:
                    await _checkpoint(f"canvas_sync_exception:{post_round}")
                    pass

            if not synced_post_graph and pw.get("last_apply_result"):
                ap = pw["last_apply_result"]
                ctx.last_apply_result_ref[0] = (
                    ap if isinstance(ap, dict) and not inspect.isawaitable(ap) else {}
                )
                await _checkpoint(f"synced_last_apply_result_from_agent:{post_round}")

            post_errors = post_response.get("workflow_errors") or []
            await _checkpoint(
                f"workflow_errors:{post_round}:{len(post_errors) if isinstance(post_errors, list) else 'na'}"
            )
            if post_errors and ctx.is_current_run(ctx.token):
                await _checkpoint(f"toast_workflow_error:{post_round}")
                await ctx.toast(f"Workflow error: {post_errors[0][1][:120]}")
                await _checkpoint(f"toast_sent:{post_round}")

        except Exception:
            await _checkpoint(f"round_exception:{post_round}")
            pass

        ctx.set_inline_status(None)
        await _checkpoint(f"clear_inline_status:{post_round}")

    await _checkpoint("end")
