"""Shared bindings for one agents-chat turn.

Built in ``chat.py``, consumed by ``gui.chat.role_turns``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeGuard, TypeVar

from agents.chat.agent_workflow.wf_response_schema import (
    AgentWorkflowResponse,
    MergeResponse,
)
from agents.chat.role_turns.protocol import (
    AppendMessageCallable,
    ApplyFromAgentCallable,
    GetRecentChangesCallable,
    IsCurrentRunCallable,
    PersistHistoryDebouncedCallable,
    RecordLlmPromptViewCallable,
    SetGraphCallable,
    SetInlineStatusCallable,
    ToastCallable,
    WorkflowDebugLogCallable,
    WorkflowStreamingRunner,
)
from agents.chat.session.state import ChatSessionState
from agents.roles.types import RoleConfig
from core.schemas.graph_edit_api import (
    AgentApplyWorkflowEditsResult,
    ApplyWorkflowEditsResult,
)
from core.schemas.primitives import Data
from core.schemas.process_graph import ProcessGraph

T = TypeVar("T")
CallableT = TypeVar("CallableT")


def _is_callable_type[CallableT](
    value: object,
    expected_type: type[CallableT],
) -> TypeGuard[CallableT]:
    return isinstance(value, expected_type)


@dataclass
class RoleChatTurnContext:
    """Narrow environment for ``RoleChatHandler.run_turn``."""

    state: ChatSessionState
    user_message: str
    messenger: str
    role_id: str
    graph_ref: list[ProcessGraph]
    token: int
    turn_id: str
    agent_label: str
    provider: str
    cfg: RoleConfig
    rag_index_dir: Path
    rag_embedding_model: str
    mydata_dir: Path
    coding_is_allowed: bool
    contribution_is_allowed: bool
    auto_delegation_is_allowed: bool
    # Workflow graph recent changes summary (difference)
    recent_changes: str | None
    training_config_path: str | None
    dispatcher_workflow_path: str | None

    apply_from_agent: Callable[[ProcessGraph], None] | None
    set_graph: Callable[[ProcessGraph], None]
    get_recent_changes: Callable[[], str | None] | None

    last_apply_result_ref: list[
        ApplyWorkflowEditsResult | None
    ]
    stream_buffer_ref: list[str]

    is_current_run: Callable[[int], bool]
    toast: Callable[[str], Awaitable[None]]
    set_inline_status: Callable[[str | None], None]
    append_message: Callable[..., None]
    run_workflow_streaming: WorkflowStreamingRunner
    persist_history_debounced: Callable[[], None]
    workflow_debug_log: Callable[[str], None]

    record_llm_prompt_view: Callable[[MergeResponse], None] | None = field(
        default=None,
        kw_only=True,
    )

    delegate_request_ref: list[Data | None] | None = field(
        default=None,
        kw_only=True,
    )

    # Results published by RoleChatHandler.run_turn().
    content_ref: list[str] = field(
        default_factory=lambda: [""],
        kw_only=True,
    )

    result_ref: list[AgentApplyWorkflowEditsResult] = field(
        default_factory=list,
        kw_only=True,
    )

    response_ref: list[AgentWorkflowResponse | None] = field(
        default_factory=lambda: [None],
        kw_only=True,
    )

    follow_up_contexts_ref: list[list[str]] = field(
        default_factory=lambda: [[]],
        kw_only=True,
    )

    apply_meta_ref: list[Data] = field(
        default_factory=lambda: [{}],
        kw_only=True,
    )

    error_ref: list[Data | None] = field(
        default_factory=lambda: [None],
        kw_only=True,
    )

    @classmethod
    def from_context(
        cls,
        context: Data,
        *,
        graph_ref: list[ProcessGraph],
        token: int,
        turn_id: str,
        agent_label: str,
        last_apply_result_ref: list[
            ApplyWorkflowEditsResult | None
        ],
        delegate_request_ref: list[Data | None] | None,
        content_ref: list[str],
        result_ref: list[AgentApplyWorkflowEditsResult],
        response_ref: list[AgentWorkflowResponse | None],
        follow_up_contexts_ref: list[list[str]],
        apply_meta_ref: list[Data],
        error_ref: list[Data | None],
    ) -> RoleChatTurnContext:
        state = cls._require_type(
            context,
            "state",
            ChatSessionState,
        )

        cfg = cls._require_type(
            context,
            "cfg",
            RoleConfig,
        )

        user_message = cls._require_type(
            context,
            "user_message",
            str,
        )

        messenger = cls._require_type(
            context,
            "messenger",
            str,
        )

        role_id = cls._require_type(
            context,
            "role_id",
            str,
        )

        provider = cls._require_type(
            context,
            "provider",
            str,
        )

        rag_embedding_model = cls._require_type(
            context,
            "rag_embedding_model",
            str,
        )

        training_config_path = cls._optional_string(
            context,
            "training_config_path",
        )

        dispatcher_workflow_path = cls._optional_string(
            context,
            "dispatcher_workflow_path",
        )

        recent_changes = cls._optional_string(
            context,
            "recent_changes",
        )

        apply_from_agent = cls._optional_callable(
            context,
            "apply_from_agent",
            ApplyFromAgentCallable,
        )

        get_recent_changes = cls._optional_callable(
            context,
            "get_recent_changes",
            GetRecentChangesCallable,
        )

        return cls(
            state=state,
            user_message=user_message,
            messenger=messenger,
            role_id=role_id,
            graph_ref=graph_ref,
            token=token,
            turn_id=turn_id,
            agent_label=agent_label,
            provider=provider,
            cfg=cfg,
            rag_index_dir=cls._require_path(
                context,
                "rag_index_dir",
            ),
            rag_embedding_model=rag_embedding_model,
            mydata_dir=cls._require_path(
                context,
                "mydata_dir",
            ),
            coding_is_allowed=bool(
                context.get("coding_is_allowed", True),
            ),
            contribution_is_allowed=bool(
                context.get("contribution_is_allowed", False),
            ),
            auto_delegation_is_allowed=bool(
                context.get("auto_delegation_is_allowed", False),
            ),
            recent_changes=recent_changes,
            training_config_path=training_config_path,
            dispatcher_workflow_path=dispatcher_workflow_path,
            apply_from_agent=apply_from_agent,
            set_graph=cls._require_callable(
                context,
                "set_graph",
                SetGraphCallable,
            ),
            get_recent_changes=get_recent_changes,
            last_apply_result_ref=last_apply_result_ref,
            stream_buffer_ref=cls._require_string_list(
                context,
                "stream_buffer_ref",
            ),
            is_current_run=cls._require_callable(
                context,
                "is_current_run",
                IsCurrentRunCallable,
            ),
            toast=cls._require_callable(
                context,
                "toast",
                ToastCallable,
            ),
            set_inline_status=cls._require_callable(
                context,
                "set_inline_status",
                SetInlineStatusCallable,
            ),
            append_message=cls._require_callable(
                context,
                "append_message",
                AppendMessageCallable,
            ),
            run_workflow_streaming=cls._require_callable(
                context,
                "run_workflow_streaming",
                WorkflowStreamingRunner,
            ),
            persist_history_debounced=cls._require_callable(
                context,
                "persist_history_debounced",
                PersistHistoryDebouncedCallable,
            ),
            workflow_debug_log=cls._require_callable(
                context,
                "workflow_debug_log",
                WorkflowDebugLogCallable,
            ),
            record_llm_prompt_view=cls._optional_callable(
                context,
                "record_llm_prompt_view",
                RecordLlmPromptViewCallable,
            ),
            delegate_request_ref=delegate_request_ref,
            content_ref=content_ref,
            result_ref=result_ref,
            response_ref=response_ref,
            follow_up_contexts_ref=follow_up_contexts_ref,
            apply_meta_ref=apply_meta_ref,
            error_ref=error_ref,
        )

    @staticmethod
    def _require_value(
        context: Data,
        name: str,
    ) -> object:
        value = context.get(name)

        if value is None:
            raise ValueError(
                f"Missing required role chat context field: {name}",
            )

        return value

    @classmethod
    def _require_type(
        cls,
        context: Data,
        name: str,
        expected_type: type[T],
    ) -> T:
        value = cls._require_value(context, name)

        if not isinstance(value, expected_type):
            raise TypeError(
                f"Context field {name!r} must be "
                f"{expected_type.__name__}, "
                f"got {type(value).__name__}",
            )

        return value

    @classmethod
    def _require_path(
        cls,
        context: Data,
        name: str,
    ) -> Path:
        value = cls._require_value(context, name)

        if isinstance(value, Path):
            return value

        if isinstance(value, str):
            return Path(value)

        raise TypeError(
            f"Context field {name!r} must be a path or string, "
            f"got {type(value).__name__}",
        )

    @classmethod
    def _require_callable(
        cls,
        context: Data,
        name: str,
        expected_type: type[CallableT],
    ) -> CallableT:
        value = cls._require_value(context, name)

        if not _is_callable_type(value, expected_type):
            raise TypeError(
                f"Context field {name!r} must match "
                f"{expected_type.__name__}, "
                f"got {type(value).__name__}",
            )

        return value


    @classmethod
    def _optional_callable(
        cls,
        context: Data,
        name: str,
        expected_type: type[CallableT],
    ) -> CallableT | None:
        value = context.get(name)

        if value is None:
            return None

        if not _is_callable_type(value, expected_type):
            raise TypeError(
                f"Context field {name!r} must match "
                f"{expected_type.__name__} or None, "
                f"got {type(value).__name__}",
            )

        return value


    @classmethod
    def _optional_string(
        cls,
        context: Data,
        name: str,
    ) -> str | None:
        value = context.get(name)

        if value is not None and not isinstance(value, str):
            raise TypeError(
                f"Context field {name!r} must be string or None",
            )

        return value

    @classmethod
    def _require_string_list(
        cls,
        context: Data,
        name: str,
    ) -> list[str]:
        value = cls._require_value(context, name)

        if (
            not isinstance(value, list)
            or not all(isinstance(item, str) for item in value)
        ):
            raise TypeError(
                f"Context field {name!r} must be list[str]",
            )

        return value
