# batch_publish_helpers.py
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol, TypedDict

from agents.chat.agent_workflow.wf_response_schema import ProgressResult
from agents.chat.context.follow_up_context import FollowUpContexts
from core.schemas.graph_edit_api import AgentApplyWorkflowEditsResult
from core.schemas.process_graph import ProcessGraph

from .batch_update_publisher import BatchUpdatePublisher


class ProgressResponse(TypedDict, total=False):
    llm_user_message: str | None
    llm_system_prompt: str | None

type ApplyMeta = Mapping[str, object]
type RunOutput = Mapping[str, object]

type RoleIdGetter = Callable[[], str | None]
type AgentDisplayGetter = Callable[[], str | None]
type TurnIdGetter = Callable[[], str | None]
type MessengerGetter = Callable[[], str | None]
type FollowUpContextsGetter = Callable[
    [], FollowUpContexts | None
]
type GraphGetter = Callable[[], ProcessGraph]
type ApplyResultGetter = Callable[
    [], AgentApplyWorkflowEditsResult | None
]
type ResultGetter = Callable[[], ProgressResult]
type ContentGetter = Callable[[], str | None]
type ResponseGetter = Callable[[], ProgressResponse | None]
type ApplyMetaGetter = Callable[[], ApplyMeta | None]
type SessionLanguageGetter = Callable[[], str | None]
type RunOutputGetter = Callable[[], RunOutput | None]
type SourceGetter = Callable[[], str]


class PublishInProgress(Protocol):
    def __call__(
        self,
        *,
        stage: str,
        kind: str | None,
    ) -> None:
        ...


def make_publish_in_progress(
    *,
    batch_update_publisher: BatchUpdatePublisher | None,
    run_id: str | None = None,
    get_role_id: RoleIdGetter,
    get_agent_display: AgentDisplayGetter,
    get_turn_id: TurnIdGetter,
    get_messenger: MessengerGetter,
    get_follow_up_contexts: FollowUpContextsGetter,
    get_graph_ref: GraphGetter,
    get_last_apply_result: ApplyResultGetter,
    get_result: ResultGetter,
    get_content: ContentGetter,
    get_response: ResponseGetter,
    get_apply_meta: ApplyMetaGetter,
    get_session_language: SessionLanguageGetter,
    get_run_output: RunOutputGetter,
    get_source: SourceGetter,
) -> PublishInProgress:
    def _publish_in_progress(
        *,
        stage: str,
        kind: str | None,
    ) -> None:
        if batch_update_publisher is None:
            return

        if run_id is not None:
            batch_update_publisher._run_id = run_id

        result = get_result()
        content = get_content()
        response = get_response()
        apply_meta = get_apply_meta()
        last_apply_result = get_last_apply_result()
        run_output = get_run_output()
        role_id = get_role_id()
        agent_display = get_agent_display()
        turn_id = get_turn_id()
        session_language = get_session_language()
        messenger = get_messenger()
        run_output = get_run_output()

        if role_id is None:
            raise ValueError("role_id is required")

        if agent_display is None:
            raise ValueError("agent_display is required")

        if turn_id is None:
            raise ValueError("turn_id is required")

        if session_language is None:
            raise ValueError("session_language is required")

        if messenger is None:
            raise ValueError("messenger is required")

        llm_user_message = (
            response.get("llm_user_message")
            if response is not None
            else None
        )

        llm_system_prompt = (
            response.get("llm_system_prompt")
            if response is not None
            else None
        )

        batch_update_publisher.publish_progress(
            status={"status": stage},
            role_id=role_id,
            agent_display=agent_display,
            display_content=str(
                result.get("content_for_display")
                or content
                or ""
            ),
            turn_id=turn_id,
            source=get_source(),
            session_language=session_language,
            messenger=messenger,
            llm_user_message=llm_user_message or "",
            llm_system_prompt=llm_system_prompt or "",
            id=None,
            ts=None,
            graph=get_graph_ref(),
            parsed_edits=result.get("edits", []),
            apply_meta=apply_meta or {},
            follow_up_contexts=get_follow_up_contexts(),
            last_apply_result=last_apply_result,
            run_output=dict(run_output) if run_output is not None else None,
            error=None,
        )

    return _publish_in_progress
