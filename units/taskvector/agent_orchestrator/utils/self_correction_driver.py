import inspect
import time
import traceback

from agents.chat.agent_workflow.build_self_correction_retry_inputs import (
    build_self_correction_retry_inputs,
)
from agents.chat.agent_workflow.helpers import (
    get_runtime_for_prompts,
    refresh_last_graph_apply_result,
)
from agents.chat.agent_workflow.run_agent_workflow import run_agent_workflow
from agents.chat.context.language_control import (
    maybe_pin_session_language_from_workflow_response,
)
from agents.chat.context.todo_list_manager import augment_graph_with_client_tasks
from agents.chat.handlers.chat_turn_context import format_previous_turn
from agents.chat.role_turns.turn_edits import canonicalize_add_comment_edits
from agents.chat.session.state import AgentChatHistory
from agents.roles.types import RoleConfig
from agents.roles.workflow_designer.workflow_inputs import default_wf_language_hint
from core.schemas import ProcessGraph
from core.schemas.graph_edit_api import (
    AgentApplyWorkflowEditsResult,
    ApplyWorkflowEditsResult,
    GraphEdit,
)
from core.schemas.primitives import Data
from runtime.executor import GraphStreamCallback
from units.taskvector.agent_orchestrator.utils.proxies import SessionProxy


async def run_self_correction_retry_async(
    failed_apply_result: AgentApplyWorkflowEditsResult,
    session: SessionProxy,
    role_config: RoleConfig,
    graph_ref: list[ProcessGraph],
    last_apply_result_ref: list[AgentApplyWorkflowEditsResult],
    wf_language_hint: list[str],
    stream_cb: GraphStreamCallback| None,
    history: AgentChatHistory,
    recent_changes: str | None,
    coding_is_allowed: bool,
    contribution_is_allowed: bool,
    role_id: str,
) -> tuple[Data, object, str | None]:
    """
    Async wrapper for _run_self_correction_retry that runs blocking parts in threadpool.
    Returns (retry_response, retry_result_dict_or_None, retry_reply_or_None).
    """

    # --- Logging ---
    async def _checkpoint(name: str) -> None:
        # replace print with your logger if available
        print(f"[self_correction_driver] checkpoint: {name} ts={time.time():.3f}")

    async def _await_with_log(name: str, awaitable):
        t0 = time.time()
        try:
            await _checkpoint(f"enter:{name}")
            res = await awaitable
            print(f"[self_correction_driver] done:{name} dt={time.time() - t0:.3f}s")
            return res
        except Exception as exc:
            print(
                f"[self_correction_driver] FAIL:{name} dt={time.time() - t0:.3f}s exc={type(exc).__name__}: {exc}"
            )
            traceback.print_exc()
            raise

    # --- end Logging ---

    # access workflow_path and param overrides through RoleChatConfig
    chat_config = role_config.chat

    if chat_config is None:
        print(
            f"[self_correction_driver] no chat configuration "
            f"for role_id={role_config.id!r}"
        )
        return {}, None, None
    # agent role workflow path
    agent_workflow_path = chat_config.workflow
    # workflow units param overrides
    overrides = chat_config.overrides

    if not agent_workflow_path:
        print(
            f"[self_correction_driver] no workflow configured "
            f"for role_id={role_config.id!r}"
        )
        return {}, None, None

    _graph = graph_ref[0]

    _runtime = await _await_with_log(
        "get_runtime_for_prompts", get_runtime_for_prompts(_graph)
    )
    _previous_turn = await _await_with_log(
        "format_previous_turn", format_previous_turn(history)
    )

    retry_inputs = build_self_correction_retry_inputs(
        failed_apply_result,
        _graph,
        recent_changes,
        runtime=_runtime,
        coding_is_allowed=coding_is_allowed,
        contribution_is_allowed=contribution_is_allowed,
        previous_turn=_previous_turn,
        language_hint=wf_language_hint[0],
        session_language=session.session_language,
    )

    try:
        retry_response = await _await_with_log(
            "run_agent_workflow",
            run_agent_workflow(
                retry_inputs,
                overrides,
                None,
                stream_cb,
                workflow_path=agent_workflow_path,
            ),
        )
    except (TypeError, RuntimeError):
        # return empty on failure
        return {}, None, None

    await _checkpoint("after:run_agent_workflow")

    maybe_pin_session_language_from_workflow_response(session, retry_response)
    wf_language_hint[0] = default_wf_language_hint(session.session_language)

    r_result = retry_response.get("result") or {}

    raw_retry_edits = r_result.get("edits")

    if raw_retry_edits is None:
        retry_edits: list[GraphEdit] = []
    elif not isinstance(raw_retry_edits, list):
        raise TypeError(
            "Workflow result field 'edits' must be a list or null"
        )
    else:
        retry_edits = []

        for index, raw_edit in enumerate(raw_retry_edits):
            if not isinstance(raw_edit, GraphEdit):
                raise TypeError(
                    f"Workflow result field 'edits[{index}]' "
                    "must be a GraphEdit"
                )

            retry_edits.append(raw_edit)

    await _await_with_log(
        "canonicalize_add_comment_edits",
        canonicalize_add_comment_edits(
            retry_edits,
            agent_role_id=role_id,
        ),
    )
    # >>> ADDED: post-canonicalize probes <<<
    await _checkpoint(f"post-canonicalize r_result_keys={list(r_result.keys())[:20]}")
    await _checkpoint(
        f"post-canonicalize kind={r_result.get('kind')} has_graph={r_result.get('graph') is not None}"
    )
    await _checkpoint(
        f"post-canonicalize edits_type={type(r_result.get('edits')).__name__}"
    )
    # <<< ADDED END <<<

    r_kind = r_result.get("kind")
    retry_content: str | None = None

    if r_kind == "applied" and r_result.get("graph") is not None:
        raw_graph = r_result["graph"]

        if isinstance(raw_graph, ProcessGraph):
            graph_to_apply = raw_graph
        elif isinstance(raw_graph, dict):
            graph_to_apply = ProcessGraph.model_validate(raw_graph)
        else:
            graph_to_apply = None

        if graph_to_apply is not None:
            await _checkpoint("applied:before augment_graph_with_client_tasks")

            graph_to_apply, _retry_supp = await augment_graph_with_client_tasks(
                graph_to_apply,
                r_result.get("edits") or [],
                coding_is_allowed=coding_is_allowed,
            )

            await _checkpoint("applied:after augment_graph_with_client_tasks")

            try:
                from agents.chat.agent_workflow.helpers import (
                    validate_graph_to_apply_for_canvas_async,
                )

                await _checkpoint("applied:before validate_graph_to_apply_for_canvas")

                vg, v_err = await _await_with_log(
                    "validate_graph_to_apply_for_canvas",
                    validate_graph_to_apply_for_canvas_async(graph_to_apply),
                )

                await _checkpoint("applied:after validate_graph_to_apply_for_canvas")

                if not v_err and vg is not None:
                    graph_to_apply = vg
                else:
                    graph_to_apply = None

            except (TypeError, RuntimeError):
                if graph_to_apply is not None:
                    graph_ref[0] = graph_to_apply

                    await _checkpoint(
                        "applied:before refresh_last_graph_apply_result"
                    )

                    refresh_apply_result = ApplyWorkflowEditsResult(
                        success=True,
                        graph=graph_ref[0],
                        error=None,
                    )

                    last_apply_result_ref[0] = (
                        await refresh_last_graph_apply_result(
                            last_apply_result_ref[0],
                            refresh_apply_result,
                            supplement_summary="",
                        )
                    )

                    await _checkpoint(
                        "applied:after refresh_last_graph_apply_result"
                    )

        retry_raw = retry_response.get("reply") or ""
        retry_content = (
            retry_raw if isinstance(retry_raw, str) else str(retry_raw or "")
        ).strip() or None

        await _checkpoint(f"branch:applied end kind={r_kind}")

    elif r_kind == "apply_failed":
        failed_apply_raw = (
            r_result.get("last_apply_result")
            or r_result.get("apply_result")
        )

        if inspect.isawaitable(failed_apply_raw):
            failed_apply_raw = await failed_apply_raw

        if isinstance(failed_apply_raw, AgentApplyWorkflowEditsResult):
            last_apply_result_ref[0] = failed_apply_raw

        elif isinstance(failed_apply_raw, dict):
            last_apply_result_ref[0] = (
                AgentApplyWorkflowEditsResult.model_validate(failed_apply_raw)
            )

        elif isinstance(failed_apply_raw, ApplyWorkflowEditsResult):
            last_apply_result_ref[0] = AgentApplyWorkflowEditsResult(
                attempted=True,
                apply_result=failed_apply_raw,
            )

        else:
            last_apply_result_ref[0] = AgentApplyWorkflowEditsResult(
                attempted=True,
                apply_result=ApplyWorkflowEditsResult(
                    success=False,
                    graph=graph_ref[0],
                    error="Workflow edit application failed.",
                ),
            )

        await _checkpoint(f"branch:apply_failed end kind={r_kind}")

    await _checkpoint(f"exit role_id={role_id} kind={r_kind}")

    return retry_response, r_result, retry_content
