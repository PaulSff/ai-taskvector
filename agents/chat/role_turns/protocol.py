"""Protocol for one agents-chat role (one ``role_id``)."""

from __future__ import annotations

from collections.abc import Awaitable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from agents.chat.agent_workflow.wf_response_schema import (
    AgentWorkflowResponse,
    MergeResponse,
)
from core.schemas.primitives import WorkflowInputs
from core.schemas.process_graph import ProcessGraph
from runtime.executor import GraphStreamCallback

if TYPE_CHECKING:
    from agents.chat.context.role_turn_context import RoleChatTurnContext

@runtime_checkable
class SetGraphCallable(Protocol):
    def __call__(self, graph: ProcessGraph) -> None:
        ...


@runtime_checkable
class IsCurrentRunCallable(Protocol):
    def __call__(self, token: int) -> bool:
        ...


@runtime_checkable
class ToastCallable(Protocol):
    def __call__(self, message: str) -> Awaitable[None]:
        ...


@runtime_checkable
class SetInlineStatusCallable(Protocol):
    def __call__(self, status: str | None) -> None:
        ...


@runtime_checkable
class AppendMessageCallable(Protocol):
    def __call__(self, *args: object, **kwargs: object) -> None:
        ...


@runtime_checkable
class PersistHistoryDebouncedCallable(Protocol):
    def __call__(self) -> None:
        ...


@runtime_checkable
class WorkflowDebugLogCallable(Protocol):
    def __call__(self, message: str) -> None:
        ...


@runtime_checkable
class ApplyFromAgentCallable(Protocol):
    def __call__(self, graph: ProcessGraph) -> None:
        ...


@runtime_checkable
class GetRecentChangesCallable(Protocol):
    def __call__(self) -> str | None:
        ...


@runtime_checkable
class RecordLlmPromptViewCallable(Protocol):
    def __call__(self, response: MergeResponse) -> None:
        ...

@runtime_checkable
class RoleChatHandler(Protocol):
    """Owns one role's chat turn: initial inputs, workflow path, and optional post-workflow hooks.

    Dev (-dev): after each workflow run, call ``record_llm_prompt_view_if_present(response, ctx.record_llm_prompt_view)``
    if the role’s runner merges ``attach_llm_prompt_debug_from_outputs`` into ``response`` (see ``llm_prompt_inspector``).
    """

    @property
    def role_id(self) -> str: ...

    @property
    def role_name(self) -> str: ...

    async def run_turn(
        self, ctx: RoleChatTurnContext, *, message_for_workflow: str
    ) -> None:
        """Run a single user → agent turn for this role (see ``RoleChatTurnContext``)."""
        ...

class WorkflowRunner(Protocol):
    def __call__(
        self,
        initial_inputs: WorkflowInputs | None = None,
        unit_param_overrides: WorkflowInputs | None = None,
        execution_timeout_s: float | None = None,
        *,
        stream_callback: GraphStreamCallback | None = None,
        workflow_path: str | Path | None = None,
    ) -> Awaitable[AgentWorkflowResponse]:
        ...

@runtime_checkable
class WorkflowStreamingRunner(Protocol):
    async def __call__(
        self,
        func: WorkflowRunner,
        initial_inputs: WorkflowInputs | None = None,
        unit_param_overrides: WorkflowInputs | None = None,
        execution_timeout_s: float | None = None,
        *,
        _run_token: object | None = None,
        workflow_path: str | Path | None = None,
    ) -> AgentWorkflowResponse:
        ...
