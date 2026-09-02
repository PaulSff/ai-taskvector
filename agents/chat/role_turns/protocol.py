"""Protocol for one agents-chat role (one ``role_id``)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol, runtime_checkable

from agents.chat.agent_workflow.wf_response_schema import AgentWorkflowResponse
from agents.chat.role_turns.context import RoleChatTurnContext
from core.schemas.primitives import WorkflowInputs
from runtime.executor import GraphStreamCallback


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
