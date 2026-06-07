"""
Sync agent turn runner: unpacks context dict and drives the full orchestration pipeline.

Called from AgentOrchestrator._agent_orchestrator_step (sync unit step function).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# ─── Tiny helpers ────────────────────────────────────────────────────────────


def _new_id() -> str:
    """uuid4 hex string."""
    from uuid import uuid4

    return uuid4().hex


def _now_ts() -> str:
    """ISO-8601 timestamp (seconds precision)."""
    return datetime.now().isoformat(timespec="seconds")


def _coerce_graph(g: Any) -> dict | None:
    """Convert ProcessGraph/dict/None to a plain dict for output ports."""
    if g is None:
        return None
    if hasattr(g, "model_dump"):
        return g.model_dump(by_alias=True)
    if isinstance(g, dict):
        return g
    return None


# ─── Proxy objects ────────────────────────────────────────────────────────────


class _SessionProxy:
    """
    Minimal session state object satisfying the _SessionLanguageSink protocol
    from gui.chat.context.language_control.
    Also carries chat history for format_previous_turn.
    """

    def __init__(self, session_language: str = "", history: list | None = None) -> None:
        self.session_language: str = session_language
        self.history: list[Any] = history or []


class _ToolCtxProxy:
    """
    Duck-typing context proxy for follow-up tool runners.

    Satisfies every attribute accessed by the built-in tool runner set
    (grep, rag_search, web_search, browse, github, report, read_file,
    read_code_block, read_current_workflow, add_comment, todo_manager,
    formulas_calc, run_workflow).
    """

    def __init__(
        self,
        *,
        graph_ref: list[Any],
        last_apply_result_ref: list[Any],
        follow_up_contexts: list[str],
        wf_language_hint: list[str],
        overrides: dict[str, Any],
        follow_up_tool_ids: tuple[str, ...] | None,
        analyst_mode: bool,
        agent_role_id: str,
        agent_workflow_path: Path | None,
        state: _SessionProxy,
        stream_cb: Callable[[str], None] | None,
        recent_changes: str | None,
        turn_id: str,
        agent_label: str,
        max_rounds: int,
        ordered_follow_up_tools: tuple[tuple[str, str], ...] | None = None,
    ) -> None:
        self.graph_ref = graph_ref
        self.last_apply_result_ref = last_apply_result_ref
        self.follow_up_contexts = follow_up_contexts
        self.wf_language_hint = wf_language_hint
        self.overrides = overrides
        self.follow_up_tool_ids = follow_up_tool_ids
        self.analyst_mode = analyst_mode
        self.agent_role_id = agent_role_id
        self.agent_workflow_path = agent_workflow_path
        self.state = state
        self._stream_cb = stream_cb
        self._recent_changes = recent_changes
        self.turn_id = turn_id
        self.agent_label = agent_label
        self.max_rounds = max_rounds
        self.ordered_follow_up_tools = ordered_follow_up_tools
        # Headless: no Flet page
        self.page: Any = None
        self.record_llm_prompt_view: Any = None
        self.follow_up_source_response: dict[str, Any] | None = None
        # Unique token; is_current_run always returns True in headless mode
        self.token: object = object()
        self.stream_buffer_ref: list[str] = [""]

    # ── Protocol methods ──

    def is_current_run(self, t: Any) -> bool:  # noqa: ARG002
        return True

    def get_recent_changes(self) -> str | None:
        return self._recent_changes

    def get_runtime_for_prompts(self, graph: Any) -> str:
        from gui.chat.agent_workflow.helpers import get_runtime_for_prompts

        return get_runtime_for_prompts(graph)

    def format_previous_turn(self, history: list[Any]) -> str:
        from gui.chat.handlers.chat_turn_context import format_previous_turn

        return format_previous_turn(history)

    def normalize_user_message_for_workflow(self, text: str) -> str:
        from gui.chat.handlers.chat_turn_context import (
            normalize_user_message_for_workflow,
        )

        return normalize_user_message_for_workflow(text)

    def set_inline_status(self, msg: str | None) -> None:
        if self._stream_cb is not None:
            try:
                from runtime.stream_ui_signals import inline_status_stream_chunk

                self._stream_cb(inline_status_stream_chunk(msg))
            except Exception:
                pass

    def append_message(
        self,
        role: str,  # noqa: ARG002
        content: str,  # noqa: ARG002
        meta: Any = None,  # noqa: ARG002
    ) -> None:
        pass  # no-op in headless mode

    def prepare_stream_row(self) -> None:
        pass  # no-op in headless mode

    async def run_workflow_streaming(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Async bridge: runs func in a thread so the tool-runner event loop does not block."""
        kwargs.pop("_run_token", None)
        workflow_path = kwargs.pop("workflow_path", None)
        stream_cb = self._stream_cb

        def _run() -> Any:
            if workflow_path is not None:
                return func(
                    *args, workflow_path=workflow_path, stream_callback=stream_cb
                )
            return func(*args, stream_callback=stream_cb)

        return await asyncio.to_thread(_run)

    async def toast(self, msg: str) -> None:  # noqa: ARG002
        pass  # no-op in headless mode


# ─── Role config ──────────────────────────────────────────────────────────────


def _get_role_config(role_id: str, ctx: dict[str, Any]) -> dict[str, Any]:
    """
    Build role execution config: workflow_path, overrides, analyst_mode, tool lists,
    max_follow_ups.
    """
    from agents.roles.registry import (
        ANALYST_ROLE_ID,
        RL_COACH_ROLE_ID,
        get_role,
    )
    from agents.roles.workflow_path import get_role_chat_workflow_path
    from agents.tools.catalog import (
        ORDERED_ANALYST_TOOLS,
        ORDERED_WORKFLOW_DESIGNER_TOOLS,
        analyst_tool_ids,
        workflow_designer_tool_ids,
    )
    from gui.chat.agent_workflow.helpers import (
        build_agent_workflow_unit_param_overrides,
    )
    from gui.components.settings import get_workflow_designer_max_follow_ups

    role = get_role(role_id)
    is_analyst = role_id == ANALYST_ROLE_ID
    is_rl_coach = role_id == RL_COACH_ROLE_ID
    analyst_mode = is_analyst or is_rl_coach

    workflow_path = get_role_chat_workflow_path(role_id)
    provider = str(ctx.get("provider") or "ollama")
    cfg = dict(ctx.get("cfg") or {})
    mydata_dir = str(ctx.get("mydata_dir") or ".")
    report_output_dir = str(Path(mydata_dir) / "reports")

    overrides = build_agent_workflow_unit_param_overrides(
        provider,
        cfg,
        report_output_dir=report_output_dir,
        llm_options_role_id=role_id,
        rag_top_k_role_id=role_id,
    )

    max_follow_ups: int = (
        role.follow_up_max_rounds
        if role.follow_up_max_rounds is not None
        else get_workflow_designer_max_follow_ups()
    )

    if analyst_mode:
        ordered_tools: tuple[tuple[str, str], ...] = ORDERED_ANALYST_TOOLS
        follow_up_tool_ids: tuple[str, ...] | None = (
            role.tools if role.tools else tuple(analyst_tool_ids())
        )
    else:
        ordered_tools = ORDERED_WORKFLOW_DESIGNER_TOOLS
        follow_up_tool_ids = (
            role.tools if role.tools else tuple(workflow_designer_tool_ids())
        )

    return {
        "role_id": role_id,
        "workflow_path": workflow_path,
        "overrides": overrides,
        "analyst_mode": analyst_mode,
        "is_rl_coach": is_rl_coach,
        "max_follow_ups": max_follow_ups,
        "follow_up_tool_ids": follow_up_tool_ids,
        "ordered_follow_up_tools": ordered_tools,
    }


# ─── Initial inputs ───────────────────────────────────────────────────────────


def _build_initial_inputs(
    user_message: str,
    graph: Any,
    last_apply_result: Any,
    recent_changes: str | None,
    session_language: str,
    history: list[Any],
    wf_language_hint: str,
    *,
    follow_up_context: str = "",
    coding_is_allowed: bool = True,
    contribution_is_allowed: bool = False,
    analyst_mode: bool = False,
) -> dict[str, dict[str, Any]]:
    """Build initial_inputs for run_agent_workflow (workflow JSON injects)."""
    from agents.roles.workflow_designer.workflow_inputs import (
        build_agent_workflow_initial_inputs,
    )
    from gui.chat.agent_workflow.helpers import get_runtime_for_prompts
    from gui.chat.handlers.chat_turn_context import format_previous_turn

    runtime = get_runtime_for_prompts(graph)
    previous_turn = format_previous_turn(history)

    return build_agent_workflow_initial_inputs(
        user_message,
        graph,
        last_apply_result,
        recent_changes,
        follow_up_context,
        runtime=runtime,
        coding_is_allowed=coding_is_allowed,
        contribution_is_allowed=contribution_is_allowed,
        previous_turn=previous_turn,
        language_hint=wf_language_hint,
        session_language=session_language,
        analyst_mode=analyst_mode,
    )


# ─── Follow-up chain (sync) ────────────────────────────────────────────────────


def _run_sync_follow_up_chain(
    response: dict[str, Any],
    session: _SessionProxy,
    role_id: str,
    role_config: dict[str, Any],
    history: list[Any],
    turn_id: str,
    agent_display: str,
    follow_up_contexts: list[str],
    stream_cb: Callable[[str], None] | None,
    graph_ref: list[Any],
    last_apply_result_ref: list[Any],
    wf_language_hint: list[str],
    recent_changes: str | None,
    coding_is_allowed: bool,
    contribution_is_allowed: bool,
) -> dict[str, Any]:
    """
    Sync re-implementation of run_parser_output_follow_up_chain.

    Drives ordered tool follow-up rounds (grep, rag_search, web_search, …) using
    async tool runners bridged to the sync context via asyncio.run() in a thread pool.
    """
    from agents.prompts import WORKFLOW_DESIGNER_FOLLOW_UP_USER_MESSAGE
    from agents.roles.workflow_designer.workflow_inputs import (
        build_agent_workflow_initial_inputs,
        default_wf_language_hint,
    )
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
    from gui.chat.agent_workflow.helpers import get_runtime_for_prompts
    from gui.chat.agent_workflow.run import run_agent_workflow
    from gui.chat.context.language_control import (
        maybe_pin_session_language_from_workflow_response,
    )
    from gui.chat.context.todo_list_manager import get_summary_params
    from gui.chat.handlers.chat_turn_context import (
        format_previous_turn,
        normalize_user_message_for_workflow,
    )
    from gui.utils.workflow_output_normalizer import normalize_follow_up_parser_output

    # ── Local helpers mirroring chain.py ──

    def _wf_apply_failed(resp: dict[str, Any]) -> bool:
        r = resp.get("result") or {}
        if r.get("kind") == "apply_failed":
            return True
        st = resp.get("status")
        return (
            isinstance(st, dict)
            and st.get("attempted") is True
            and st.get("success") is False
        )

    def _wf_is_question(resp: dict[str, Any]) -> bool:
        v = resp.get("is_question")
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "y")
        return False

    def _merge_preserved(
        resp: dict[str, Any], preserved: dict[str, Any]
    ) -> dict[str, Any]:
        out = dict(resp)
        out["result"] = dict(preserved.get("result") or {})
        st = preserved.get("status")
        out["status"] = dict(st) if isinstance(st, dict) else st
        merged_errs = list(resp.get("workflow_errors") or [])
        for e in preserved.get("workflow_errors") or []:
            if e not in merged_errs:
                merged_errs.append(e)
        out["workflow_errors"] = merged_errs
        return out

    max_rounds: int = role_config["max_follow_ups"]
    overrides: dict[str, Any] = dict(role_config["overrides"])
    ordered_tools: tuple[tuple[str, str], ...] = role_config["ordered_follow_up_tools"]
    follow_up_tool_ids: tuple[str, ...] | None = role_config.get("follow_up_tool_ids")
    analyst_mode: bool = role_config["analyst_mode"]
    agent_workflow_path: Path = role_config["workflow_path"]

    def _hint() -> str:
        return wf_language_hint[0]

    proxy = _ToolCtxProxy(
        graph_ref=graph_ref,
        last_apply_result_ref=last_apply_result_ref,
        follow_up_contexts=follow_up_contexts,
        wf_language_hint=wf_language_hint,
        overrides=overrides,
        follow_up_tool_ids=follow_up_tool_ids,
        analyst_mode=analyst_mode,
        agent_role_id=role_id,
        agent_workflow_path=agent_workflow_path,
        state=session,
        stream_cb=stream_cb,
        recent_changes=recent_changes,
        turn_id=turn_id,
        agent_label=agent_display,
        max_rounds=max_rounds,
        ordered_follow_up_tools=ordered_tools,
    )

    preserved_apply_failure: dict[str, Any] | None = None

    def _capture_apply_failure(resp: dict[str, Any]) -> None:
        nonlocal preserved_apply_failure
        if not _wf_apply_failed(resp):
            return
        preserved_apply_failure = {
            "result": dict(resp.get("result") or {}),
            "status": dict(resp.get("status") or {})
            if isinstance(resp.get("status"), dict)
            else resp.get("status"),
            "workflow_errors": list(resp.get("workflow_errors") or []),
        }

    _capture_apply_failure(response)
    if _wf_is_question(response):
        return response

    for _ in range(max_rounds):
        po = normalize_follow_up_parser_output(response.get("parser_output"))
        follow_up_msg = WORKFLOW_DESIGNER_FOLLOW_UP_USER_MESSAGE.format(
            language=_hint(),
            session_language=_hint(),
        )

        # Accumulators for this round
        context_chunks: list[str] = []
        any_empty_tool = False
        read_code_ids_for_msg: list[str] = []
        implementation_links_for_types: list[str] = []
        report_follow_up = False
        formulas_calc_follow_up = False

        proxy.follow_up_source_response = response

        # Run tool runners in catalog order
        for tool_id, parser_key in ordered_tools:
            if follow_up_tool_ids is not None and tool_id not in follow_up_tool_ids:
                continue
            if not po.get(parser_key):
                continue
            runner = get_follow_up_runner(tool_id)
            if not callable(runner):
                continue
            try:
                result_obj = runner(proxy, po, language_hint=_hint)
                if inspect.isawaitable(result_obj):
                    try:
                        with concurrent.futures.ThreadPoolExecutor(
                            max_workers=1
                        ) as pool:
                            contrib = pool.submit(asyncio.run, result_obj).result(
                                timeout=30
                            )
                    except Exception:
                        contrib = None
                else:
                    contrib = result_obj
            except Exception:
                contrib = None

            if not isinstance(contrib, FollowUpContribution):
                continue

            context_chunks.extend(contrib.context_chunks)
            if contrib.any_empty_tool:
                any_empty_tool = True
            ex = contrib.extra
            if FOLLOW_UP_EXTRA_READ_CODE_IDS in ex:
                v = ex[FOLLOW_UP_EXTRA_READ_CODE_IDS]
                if isinstance(v, list):
                    read_code_ids_for_msg = [str(x) for x in v]
            if FOLLOW_UP_EXTRA_IMPLEMENTATION_LINK_TYPES in ex:
                v = ex[FOLLOW_UP_EXTRA_IMPLEMENTATION_LINK_TYPES]
                if isinstance(v, list):
                    implementation_links_for_types = [str(x) for x in v]
            if ex.get(FOLLOW_UP_EXTRA_REPORT_FOLLOW_UP):
                report_follow_up = True
            if ex.get(FOLLOW_UP_EXTRA_FORMULAS_CALC_FOLLOW_UP):
                formulas_calc_follow_up = True

        # Choose follow-up user message variant
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

        if not context_chunks:
            break

        follow_up_context = "\n\n---\n\n".join(context_chunks)
        follow_up_contexts.append(follow_up_context)

        _graph = graph_ref[0]
        _gd = _coerce_graph(_graph)
        _runtime = get_runtime_for_prompts(_graph)

        if analyst_mode:
            gs: dict[str, Any] = dict(overrides.get("graph_summary") or {})
            gs.setdefault("include_structure", False)
            gs.setdefault("include_code_block_source", False)
        else:
            gs = get_summary_params(coding_is_allowed, _gd)

        ul_base = dict(overrides.get("units_library") or {})
        if implementation_links_for_types:
            ul_merged: dict[str, Any] = {
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

        follow_up_overrides: dict[str, Any] = {
            **overrides,
            "graph_summary": gs,
            "rag_search": {**(overrides.get("rag_search") or {}), "ignore": True},
            "units_library": ul_merged,
        }

        follow_up_user_msg = normalize_user_message_for_workflow(follow_up_msg)
        follow_up_inputs = build_agent_workflow_initial_inputs(
            follow_up_user_msg,
            _graph,
            last_apply_result_ref[0],
            recent_changes,
            follow_up_context,
            runtime=_runtime,
            coding_is_allowed=coding_is_allowed,
            contribution_is_allowed=contribution_is_allowed,
            previous_turn=format_previous_turn(history),
            language_hint=_hint(),
            session_language=session.session_language,
            analyst_mode=analyst_mode,
        )

        try:
            response = run_agent_workflow(
                follow_up_inputs,
                follow_up_overrides,
                None,
                stream_callback=stream_cb,
                workflow_path=agent_workflow_path,
            )
        except Exception:
            break

        maybe_pin_session_language_from_workflow_response(session, response)
        wf_language_hint[0] = default_wf_language_hint(session.session_language)

        if _wf_is_question(response):
            break
        _capture_apply_failure(response)

    # Restore preserved apply failure if the final response is not "applied"
    if preserved_apply_failure is not None:
        final_r = response.get("result") or {}
        if final_r.get("kind") != "applied":
            response = _merge_preserved(response, preserved_apply_failure)

    return response


# ─── Graph apply & augment ─────────────────────────────────────────────────────


def _apply_and_augment_graph(
    graph_to_apply: Any,
    edits: list[Any],
    ctx: dict[str, Any],
    graph_ref: list[Any],
    last_apply_result_ref: list[Any],
) -> tuple[Any, list[str], str | None]:
    """
    Augment graph with client-side todo tasks, validate for canvas, update refs.
    Returns (validated_graph_or_None, supplement_strings, validation_error_or_None).
    """
    from gui.chat.agent_workflow.helpers import (
        refresh_last_apply_result_after_canvas_apply,
    )
    from gui.chat.context.todo_list_manager import augment_graph_with_client_tasks

    coding_is_allowed = bool(ctx.get("coding_is_allowed", True))
    supplements: list[str] = []
    v_err: str | None = None

    if isinstance(graph_to_apply, dict):
        graph_to_apply, supplements = augment_graph_with_client_tasks(
            graph_to_apply,
            edits,
            coding_is_allowed=coding_is_allowed,
        )
        try:
            from gui.components.workflow_tab.workflows.core_workflows import (
                validate_graph_to_apply_for_canvas,
            )

            vg, v_err = validate_graph_to_apply_for_canvas(graph_to_apply)
            if v_err or vg is None:
                graph_to_apply = None
            else:
                graph_to_apply = vg
        except Exception:
            # Headless mode: canvas validation unavailable; keep the dict as-is.
            pass

    if graph_to_apply is not None:
        graph_ref[0] = graph_to_apply
        last_apply_result_ref[0] = refresh_last_apply_result_after_canvas_apply(
            last_apply_result_ref[0],
            graph_ref[0],
            supplement_summary="; ".join(supplements),
        )

    return graph_to_apply, supplements, v_err


# ─── Post-apply follow-up ─────────────────────────────────────────────────────


def _run_post_apply_follow_up(
    response: dict[str, Any],  # noqa: ARG001
    result: dict[str, Any],
    session: _SessionProxy,
    role_config: dict[str, Any],
    messages: list[dict[str, Any]],  # noqa: ARG001
    turn_id: str,  # noqa: ARG001
    agent_display: str,  # noqa: ARG001
    follow_up_contexts: list[str],  # noqa: ARG001
    graph_ref: list[Any],
    last_apply_result_ref: list[Any],
    wf_language_hint: list[str],
    stream_cb: Callable[[str], None] | None,
    is_cancelled: Callable[[], bool],  # noqa: ARG001
    parser_chain_runner: Callable[[dict[str, Any]], dict[str, Any]],
    history: list[Any],
    recent_changes: str | None,
    coding_is_allowed: bool,
    contribution_is_allowed: bool,
    role_id: str,
) -> str:
    """
    Sync post-apply review rounds (import / todo / comment / default).
    Returns the accumulated display content string.
    """
    import agents.follow_ups as agents_follow_ups
    from agents.prompts import (
        WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP,
        WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP_USER_MESSAGE,
        WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP,
        WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP_USER_MESSAGE,
        WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP,
        WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP_USER_MESSAGE,
        WORKFLOW_DESIGNER_TODO_FOLLOW_UP,
        WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE,
    )
    from agents.roles.workflow_designer.workflow_inputs import (
        build_agent_workflow_initial_inputs,
        default_wf_language_hint,
    )
    from gui.chat.agent_workflow.helpers import (
        get_runtime_for_prompts,
        refresh_last_apply_result_after_canvas_apply,
    )
    from gui.chat.agent_workflow.run import run_agent_workflow
    from gui.chat.context.language_control import (
        maybe_pin_session_language_from_workflow_response,
    )
    from gui.chat.context.todo_list_manager import (
        augment_graph_with_client_tasks,
        get_summary_params,
        graph_has_any_open_tasks,
    )
    from gui.chat.handlers.chat_turn_context import (
        format_previous_turn,
        normalize_user_message_for_workflow,
    )
    from gui.chat.role_turns.turn_edits import canonicalize_add_comment_edits

    max_rounds: int = role_config["max_follow_ups"]
    overrides: dict[str, Any] = dict(role_config["overrides"])
    agent_workflow_path: Path = role_config["workflow_path"]
    analyst_mode: bool = role_config["analyst_mode"]

    edits = result.get("edits") or []
    _TODO_ACTIONS = frozenset(
        {
            "add_todo_list",
            "remove_todo_list",
            "add_task",
            "remove_task",
            "mark_completed",
        }
    )
    had_import_workflow = any(
        isinstance(e, dict) and e.get("action") == "import_workflow" for e in edits
    )
    had_todo = any(
        isinstance(e, dict) and e.get("action") in _TODO_ACTIONS for e in edits
    )
    had_add_comment = any(
        isinstance(e, dict) and e.get("action") == "add_comment" for e in edits
    )

    def _hint() -> str:
        return wf_language_hint[0]

    def _post_apply_messages(round_idx: int) -> tuple[str, str] | None:
        if round_idx == 0:
            if had_import_workflow:
                return (
                    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP.format(
                        language=_hint(), session_language=_hint()
                    ),
                    WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP_USER_MESSAGE.format(
                        language=_hint(), session_language=_hint()
                    ),
                )
            if had_add_comment and had_todo:
                return (
                    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP.format(
                        language=_hint(), session_language=_hint()
                    ),
                    WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP_USER_MESSAGE.format(
                        language=_hint(), session_language=_hint()
                    ),
                )
            if had_add_comment:
                return (
                    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP.format(
                        language=_hint(), session_language=_hint()
                    ),
                    WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP_USER_MESSAGE.format(
                        language=_hint(), session_language=_hint()
                    ),
                )
            if had_todo:
                return (
                    WORKFLOW_DESIGNER_TODO_FOLLOW_UP.format(
                        language=_hint(), session_language=_hint()
                    ),
                    WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE.format(
                        language=_hint(), session_language=_hint()
                    ),
                )
            return (
                agents_follow_ups.DEFAULT_POST_APPLY_FOLLOW_UP_INJECT.format(
                    language=_hint(), session_language=_hint()
                ),
                agents_follow_ups.DEFAULT_POST_APPLY_FOLLOW_UP_USER_MESSAGE.format(
                    language=_hint(), session_language=_hint()
                ),
            )
        if not graph_has_any_open_tasks(graph_ref[0]):
            return None
        return (
            WORKFLOW_DESIGNER_TODO_FOLLOW_UP.format(
                language=_hint(), session_language=_hint()
            ),
            WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE.format(
                language=_hint(), session_language=_hint()
            ),
        )

    content = str(result.get("content_for_display") or "")

    for post_round in range(max_rounds):
        pair = _post_apply_messages(post_round)
        if pair is None:
            break
        post_msg, post_user_msg = pair

        try:
            post_user_msg = normalize_user_message_for_workflow(post_user_msg)
            _graph = graph_ref[0]
            _gd_post = _coerce_graph(_graph)

            if isinstance(_gd_post, dict):
                if analyst_mode:
                    gs: dict[str, Any] = dict(overrides.get("graph_summary") or {})
                    gs.setdefault("include_structure", False)
                    gs.setdefault("include_code_block_source", False)
                    overrides["graph_summary"] = gs
                else:
                    overrides["graph_summary"] = get_summary_params(
                        coding_is_allowed, _gd_post
                    )

            _runtime = get_runtime_for_prompts(_graph)
            post_inputs = build_agent_workflow_initial_inputs(
                post_user_msg,
                _graph,
                last_apply_result_ref[0],
                recent_changes,
                post_msg,
                runtime=_runtime,
                coding_is_allowed=coding_is_allowed,
                contribution_is_allowed=contribution_is_allowed,
                previous_turn=format_previous_turn(history),
                language_hint=_hint(),
                session_language=session.session_language,
                analyst_mode=analyst_mode,
            )

            post_response = run_agent_workflow(
                post_inputs,
                overrides,
                None,
                stream_callback=stream_cb,
                workflow_path=agent_workflow_path,
            )

            post_chained = parser_chain_runner(post_response)
            if post_chained is None:
                return content
            post_response = post_chained

            maybe_pin_session_language_from_workflow_response(session, post_response)
            wf_language_hint[0] = default_wf_language_hint(session.session_language)

            post_raw = post_response.get("reply")
            if isinstance(post_raw, dict) and "action" in post_raw:
                post_raw = post_raw.get("action") or ""
            post_reply = (
                post_raw if isinstance(post_raw, str) else str(post_raw or "")
            ).strip()

            if post_reply:
                content = content + "\n\n" + post_reply
                result["content_for_display"] = content

            # Handle applied inside a post-apply round
            pw = post_response.get("result") or {}
            post_kind = pw.get("kind")
            post_graph = pw.get("graph")
            if post_kind == "applied" and post_graph is not None:
                try:
                    if isinstance(post_graph, dict):
                        _post_edits = pw.get("edits") or []
                        canonicalize_add_comment_edits(
                            _post_edits, agent_role_id=role_id
                        )
                        post_graph, _post_supp = augment_graph_with_client_tasks(
                            post_graph,
                            _post_edits,
                            coding_is_allowed=coding_is_allowed,
                        )
                        try:
                            from gui.components.workflow_tab.workflows.core_workflows import (
                                validate_graph_to_apply_for_canvas,
                            )

                            post_pg, _p_err = validate_graph_to_apply_for_canvas(
                                post_graph
                            )
                        except Exception:
                            post_pg = post_graph
                    else:
                        post_pg = post_graph
                    if post_pg is not None:
                        graph_ref[0] = post_pg
                        last_apply_result_ref[0] = (
                            refresh_last_apply_result_after_canvas_apply(
                                last_apply_result_ref[0],
                                graph_ref[0],
                                supplement_summary="",
                            )
                        )
                except Exception:
                    pass

            # Stop if agent asked a question
            v_q = post_response.get("is_question")
            is_q = (
                v_q
                if isinstance(v_q, bool)
                else (
                    bool(v_q)
                    if isinstance(v_q, (int, float))
                    else (
                        isinstance(v_q, str)
                        and v_q.strip().lower() in ("1", "true", "yes", "y")
                    )
                )
            )
            if is_q:
                break

        except Exception:
            pass

    return content


# ─── Self-correction retry ────────────────────────────────────────────────────


def _run_self_correction_retry(
    failed_apply_result: dict[str, Any],
    session: _SessionProxy,
    role_config: dict[str, Any],
    graph_ref: list[Any],
    last_apply_result_ref: list[Any],
    wf_language_hint: list[str],
    stream_cb: Callable[[str], None] | None,
    history: list[Any],
    recent_changes: str | None,
    coding_is_allowed: bool,
    contribution_is_allowed: bool,
    role_id: str,
) -> tuple[dict[str, Any], Any, str | None]:
    """
    Same-turn self-correction after apply_failed.
    Returns (retry_response, retry_result_dict_or_None, retry_reply_or_None).
    """
    from agents.roles.workflow_designer.workflow_inputs import default_wf_language_hint
    from gui.chat.agent_workflow.helpers import (
        build_self_correction_retry_inputs,
        get_runtime_for_prompts,
        refresh_last_apply_result_after_canvas_apply,
    )
    from gui.chat.agent_workflow.run import run_agent_workflow
    from gui.chat.context.language_control import (
        maybe_pin_session_language_from_workflow_response,
    )
    from gui.chat.context.todo_list_manager import augment_graph_with_client_tasks
    from gui.chat.handlers.chat_turn_context import format_previous_turn
    from gui.chat.role_turns.turn_edits import canonicalize_add_comment_edits

    overrides = role_config["overrides"]
    agent_workflow_path: Path = role_config["workflow_path"]

    _graph = graph_ref[0]
    _runtime = get_runtime_for_prompts(_graph)

    retry_inputs = build_self_correction_retry_inputs(
        failed_apply_result,
        _graph,
        recent_changes,
        runtime=_runtime,
        coding_is_allowed=coding_is_allowed,
        contribution_is_allowed=contribution_is_allowed,
        previous_turn=format_previous_turn(history),
        language_hint=wf_language_hint[0],
        session_language=session.session_language,
    )

    try:
        retry_response = run_agent_workflow(
            retry_inputs,
            overrides,
            None,
            stream_callback=stream_cb,
            workflow_path=agent_workflow_path,
        )
    except Exception:
        return {}, None, None

    maybe_pin_session_language_from_workflow_response(session, retry_response)
    wf_language_hint[0] = default_wf_language_hint(session.session_language)

    r_result = retry_response.get("result") or {}
    canonicalize_add_comment_edits(r_result.get("edits"), agent_role_id=role_id)
    r_kind = r_result.get("kind")
    retry_content: str | None = None

    if r_kind == "applied" and r_result.get("graph") is not None:
        graph_to_apply = r_result["graph"]
        if isinstance(graph_to_apply, dict):
            graph_to_apply, _retry_supp = augment_graph_with_client_tasks(
                graph_to_apply,
                r_result.get("edits") or [],
                coding_is_allowed=coding_is_allowed,
            )
            try:
                from gui.components.workflow_tab.workflows.core_workflows import (
                    validate_graph_to_apply_for_canvas,
                )

                vg, v_err = validate_graph_to_apply_for_canvas(graph_to_apply)
                if not v_err and vg is not None:
                    graph_to_apply = vg
                else:
                    graph_to_apply = None
            except Exception:
                pass
        if graph_to_apply is not None:
            graph_ref[0] = graph_to_apply
            last_apply_result_ref[0] = refresh_last_apply_result_after_canvas_apply(
                last_apply_result_ref[0], graph_ref[0], supplement_summary=""
            )
        retry_raw = retry_response.get("reply") or ""
        retry_content = (
            retry_raw if isinstance(retry_raw, str) else str(retry_raw or "")
        ).strip() or None
    elif r_kind == "apply_failed":
        last_apply_result_ref[0] = r_result.get("last_apply_result") or r_result.get(
            "apply_result"
        )

    return retry_response, r_result, retry_content


# ─── Main entry point ─────────────────────────────────────────────────────────


def run_orchestrator_turn(
    context: dict[str, Any],
    *,
    stream_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Run one complete agent turn and return structured output port values.

    Drives: initial workflow → follow-up chain → apply/validate → post-apply rounds.

    Args:
        context: See AgentOrchestrator module docstring for accepted keys.
        stream_callback: Called for each LLM token chunk (same as all streaming units).

    Returns:
        Dict with keys: status, token, message, role, error.
    """
    from agents.roles.registry import (
        WORKFLOW_DESIGNER_ROLE_ID,
        get_role,
    )
    from agents.roles.workflow_designer.workflow_inputs import default_wf_language_hint
    from gui.chat.agent_workflow.run import run_agent_workflow
    from gui.chat.context.language_control import (
        finalize_workflow_designer_turn_session_language,
        maybe_pin_session_language_from_workflow_response,
    )
    from gui.chat.handlers.chat_turn_context import normalize_user_message_for_workflow
    from gui.chat.role_turns.turn_edits import canonicalize_add_comment_edits
    from gui.utils.workflow_output_normalizer import (
        apply_meta_with_formulas_calc_tool_status,
        formulas_calc_display_appendix,
    )
    from runtime.run import WorkflowTimeoutError

    # ── Unpack context ──

    user_message = normalize_user_message_for_workflow(
        context.get("user_message") or ""
    )
    messenger = str(context.get("messenger") or "")
    role_id = (
        str(
            context.get("role_id")
            or context.get("role_hint")
            or WORKFLOW_DESIGNER_ROLE_ID
        ).strip()
        or WORKFLOW_DESIGNER_ROLE_ID
    )

    history: list[Any] = list(context.get("history") or [])
    session_language = str(context.get("session_language") or "")
    last_apply_result: dict[str, Any] | None = context.get("last_apply_result")
    graph: Any = context.get("graph")
    recent_changes: str | None = context.get("recent_changes")
    provider = str(context.get("provider") or "ollama")
    cfg = dict(context.get("cfg") or {})
    mydata_dir = str(context.get("mydata_dir") or ".")
    coding_is_allowed = bool(context.get("coding_is_allowed", True))
    contribution_is_allowed = bool(context.get("contribution_is_allowed", False))

    # ── Mutable references ──

    graph_ref: list[Any] = [graph]
    last_apply_result_ref: list[Any] = [last_apply_result]
    wf_language_hint: list[str] = [default_wf_language_hint(session_language)]
    session = _SessionProxy(session_language=session_language, history=history)

    # ── Role resolution ──

    try:
        role = get_role(role_id)
    except Exception:
        role_id = WORKFLOW_DESIGNER_ROLE_ID
        role = get_role(role_id)
    agent_display = role.role_name or role_id

    # ── Role config ──

    try:
        role_config = _get_role_config(
            role_id,
            {
                "provider": provider,
                "cfg": cfg,
                "mydata_dir": mydata_dir,
                "coding_is_allowed": coding_is_allowed,
                "contribution_is_allowed": contribution_is_allowed,
            },
        )
    except Exception as exc:
        return {
            "status": None,
            "token": None,
            "message": None,
            "role": None,
            "error": {"type": "error", "error": f"Role config failed: {exc}"},
        }

    turn_id = _new_id()
    messages: list[dict[str, Any]] = []
    follow_up_contexts: list[str] = []

    # ── Build initial workflow inputs ──

    initial_inputs = _build_initial_inputs(
        user_message,
        graph,
        last_apply_result,
        recent_changes,
        session_language,
        history,
        wf_language_hint[0],
        coding_is_allowed=coding_is_allowed,
        contribution_is_allowed=contribution_is_allowed,
        analyst_mode=role_config["analyst_mode"],
    )

    # ── Run main workflow ──

    response: dict[str, Any] = {}
    content = ""
    result: dict[str, Any] = {}

    try:
        response = run_agent_workflow(
            initial_inputs,
            role_config["overrides"],
            None,  # execution_timeout_s → DEFAULT_EXECUTION_TIMEOUT_S
            stream_callback=stream_callback,
            workflow_path=role_config["workflow_path"],
        )
    except WorkflowTimeoutError as ex:
        timeout_s = getattr(ex, "timeout_s", 300)
        content = (
            f"(Request timed out after {timeout_s:.0f}s. "
            "Try again or check that the LLM/service is responding.)"
        )
        result = {
            "kind": "parse_error",
            "content_for_display": content,
            "apply_result": {},
            "edits": [],
        }
        last_apply_result_ref[0] = None
    except Exception as exc:
        content = f"(Workflow error: {exc})"
        result = {
            "kind": "parse_error",
            "content_for_display": content,
            "apply_result": {},
            "edits": [],
        }
        last_apply_result_ref[0] = None
    else:
        # ── Pin session language ──

        maybe_pin_session_language_from_workflow_response(session, response)
        wf_language_hint[0] = default_wf_language_hint(session.session_language)

        # ── Check delegation ──

        dr_out = response.get("delegate_request")
        if isinstance(dr_out, dict) and dr_out.get("ok") is True:
            dt = str(dr_out.get("delegate_to") or "").strip().lower()
            if dt and dt != role_id.lower():
                return {
                    "status": None,
                    "token": None,
                    "message": {
                        "type": "delegate",
                        "delegate_to": dt,
                        "original_role": role_id,
                    },
                    "role": {"role_id": dt, "name": dt},
                    "error": None,
                }

        # ── Follow-up chain (tool rounds) ──

        def _parser_chain_runner(resp: dict[str, Any]) -> dict[str, Any]:
            return _run_sync_follow_up_chain(
                resp,
                session,
                role_id,
                role_config,
                history,
                turn_id,
                agent_display,
                follow_up_contexts,
                stream_callback,
                graph_ref,
                last_apply_result_ref,
                wf_language_hint,
                recent_changes,
                coding_is_allowed,
                contribution_is_allowed,
            )

        response = _parser_chain_runner(response)

        # ── Build content & result ──

        raw_reply = response.get("reply")
        if isinstance(raw_reply, dict) and "action" in raw_reply:
            raw_reply = raw_reply.get("action") or ""
        content = (
            raw_reply if isinstance(raw_reply, str) else str(raw_reply or "")
        ).strip() or "(No response from model.)"

        wf_result = response.get("result") or {}
        result = dict(wf_result)
        canonicalize_add_comment_edits(result.get("edits"), agent_role_id=role_id)
        result["apply_result"] = (
            response.get("status") or wf_result.get("last_apply_result") or {}
        )
        ar0 = result.get("apply_result") or {}
        if (
            result.get("kind") != "apply_failed"
            and isinstance(ar0, dict)
            and ar0.get("attempted") is True
            and ar0.get("success") is False
        ):
            result["kind"] = "apply_failed"

        result["content_for_display"] = content
        last_apply_result_ref[0] = wf_result.get("last_apply_result")

        # ── Handle applied ──

        if (
            result.get("kind") == "applied"
            and result.get("graph") is not None
            and not role_config["analyst_mode"]
        ):
            applied_graph, _supplements, _v_err = _apply_and_augment_graph(
                result["graph"],
                result.get("edits") or [],
                {"coding_is_allowed": coding_is_allowed},
                graph_ref,
                last_apply_result_ref,
            )
            if applied_graph is not None:
                content = _run_post_apply_follow_up(
                    response,
                    result,
                    session,
                    role_config,
                    messages,
                    turn_id,
                    agent_display,
                    follow_up_contexts,
                    graph_ref,
                    last_apply_result_ref,
                    wf_language_hint,
                    stream_callback,
                    lambda: False,
                    _parser_chain_runner,
                    history,
                    recent_changes,
                    coding_is_allowed,
                    contribution_is_allowed,
                    role_id,
                )

        # ── Handle apply_failed ──

        elif result.get("kind") == "apply_failed" and not role_config["analyst_mode"]:
            failed_apply = (
                result.get("last_apply_result") or result.get("apply_result") or {}
            )
            last_apply_result_ref[0] = failed_apply
            _retry_resp, retry_result, retry_content = _run_self_correction_retry(
                failed_apply,
                session,
                role_config,
                graph_ref,
                last_apply_result_ref,
                wf_language_hint,
                stream_callback,
                history,
                recent_changes,
                coding_is_allowed,
                contribution_is_allowed,
                role_id,
            )
            if retry_result and retry_result.get("kind") == "applied" and retry_content:
                content = content + "\n\n" + retry_content

        # ── Finalize session language (WD only) ──

        if role_id == WORKFLOW_DESIGNER_ROLE_ID:
            finalize_workflow_designer_turn_session_language(session, response)

    # ── Assemble final output ──

    display_content = str(result.get("content_for_display") or content)
    display_content = display_content + formulas_calc_display_appendix(response)
    apply_meta = apply_meta_with_formulas_calc_tool_status(
        response, result.get("apply_result", {})
    )

    final_message: dict[str, Any] = {
        "id": _new_id(),
        "ts": _now_ts(),
        "role": "agent",
        "content": display_content,
        "agent": agent_display,
        "turn_id": turn_id,
        "source": "agent_response",
        "workflow_response": {
            "reply": display_content,
            "result_kind": result.get("kind"),
        },
        "parsed_edits": result.get("edits", []),
        "apply": apply_meta,
        "graph": _coerce_graph(graph_ref[0]),
        "run_output": response.get("run_output") or {},
        "follow_up_contexts": follow_up_contexts,
        "last_apply_result": last_apply_result_ref[0],
        "session_language": session.session_language,
        "messenger": messenger,
    }

    return {
        "status": None,
        "token": {"type": "token", "token": display_content},
        "message": {"type": "final", "message": final_message},
        "role": {"role_id": role_id, "name": agent_display},
        "error": None,
    }
