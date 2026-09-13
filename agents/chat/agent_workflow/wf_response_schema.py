"""
outputs
├── merge_response.data  ──► MergeResponse
├── merge_errors.data    ──► MergeErrors
├── direct unit response  ──►  DirectUnitsResponse (intermediate workflow data)
└── direct unit errors  ──► WorkflowErrors (intermediate workflow errors from each unit)
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from typing import Literal, Self, TypedDict, TypeGuard, cast

from agents.tools.types import ParserOutput
from core.schemas.graph_edit_api import AgentApplyWorkflowEditsResult, GraphEdit
from core.schemas.primitives import Data, WorkflowErrors
from core.schemas.process_graph import ProcessGraph


# Units standard API:
#   Data = dict[str, object]
#   Output = tuple[Data, Data] | Data
#   WorkflowOutputs = JsonObject
#   WorkflowErrors = list[tuple[str, str]]
#
def empty_progress_result() -> ProgressResult:
    return {}

def get_progress_result(data: Data, key: str) -> ProgressResult:
    value = data.get(key)

    if value is None:
        return empty_progress_result()

    if not isinstance(value, dict):
        raise TypeError(f"{key} must be a mapping")

    return cast(ProgressResult, value)

def is_apply_result(
    value: object,
) -> TypeGuard[AgentApplyWorkflowEditsResult]:
    if not isinstance(value, dict):
        return False

    return (
        isinstance(value.get("attempted"), bool)
        and isinstance(value.get("success"), bool)
    )


# workflow modification result (e.g. TODO tasks, comments, units, connections, etc.)
class ProgressResult(TypedDict, total=False):
    content_for_display: str | None
    edits: list[GraphEdit]
    kind: Literal[
        "parse_error",
        "applied",
        "apply_failed",
    ]
    apply_result: AgentApplyWorkflowEditsResult | None
    graph: ProcessGraph | None


# merged result from all the units of the workflow
@dataclass
class MergeResponse:
    reply: str = ""
    result: ProgressResult = field(
            default_factory=empty_progress_result
        )
    status: Data = field(default_factory=dict)
    graph: ProcessGraph | None = None
    diff: Data = field(default_factory=dict)

    workflow_errors: WorkflowErrors = field(default_factory=list)

    llm_prompt: str | None = None
    llm_prompt_debug: Data | None = None
    llm_system_prompt: str | None = None
    llm_user_message: str | None = None

    parser_output: ParserOutput | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Self:
        valid_fields = {item.name for item in fields(cls)}
        unknown_fields = set(data) - valid_fields

        if unknown_fields:
            raise ValueError(
                f"Unknown fields: {', '.join(sorted(unknown_fields))}"
            )

        response = cls()

        for key, value in data.items():
            setattr(response, key, value)

        return response

# merged errors collected from error ports of all the units of the workflow
@dataclass
class MergeErrors:
    """Contents of outputs['merge_errors']['data']."""

    llm_agent: str = ""
    parser: str = ""
    process: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Self:
        valid_fields = {item.name for item in fields(cls)}
        unknown_fields = set(data) - valid_fields

        if unknown_fields:
            raise ValueError(
                f"Unknown fields: {', '.join(sorted(unknown_fields))}"
            )

        response = cls()

        for key, value in data.items():
            setattr(response, key, value)

        return response


# direct response of each unit in the workflow
@dataclass
class DirectUnitsResponse:
    """Direct unit outputs before the final merge units run."""

    llm_prompt: str | None = None
    llm_prompt_debug: Data | None = None

    parser_output: ParserOutput | None = None

    units_response: list[Data] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Self:
        valid_fields = {item.name for item in fields(cls)}
        unknown_fields = set(data) - valid_fields

        if unknown_fields:
            raise ValueError(
                f"Unknown fields: {', '.join(sorted(unknown_fields))}"
            )

        response = cls()

        for key, value in data.items():
            setattr(response, key, value)

        return response


# aggregated workflow response
@dataclass
class AgentWorkflowResponse:
    """Final response returned by run_agent_workflow."""

    merged_response: MergeResponse = field(default_factory=MergeResponse)
    merged_errors: MergeErrors = field(default_factory=MergeErrors)
    direct_units_response: DirectUnitsResponse = field(
        default_factory=DirectUnitsResponse
    )
    direct_units_errors: WorkflowErrors = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Self:
        valid_fields = {
            "merged_response",
            "merged_errors",
            "direct_units_response",
            "direct_units_errors",
        }

        unknown_fields = set(data) - valid_fields
        if unknown_fields:
            raise ValueError(
                f"Unknown fields: {', '.join(sorted(unknown_fields))}"
            )

        merged_response = data.get("merged_response", {})
        merged_errors = data.get("merged_errors", {})
        direct_units_response = data.get("direct_units_response", {})
        direct_units_errors = data.get("direct_units_errors", [])

        if not isinstance(merged_response, Mapping):
            raise TypeError("merged_response must be a mapping")

        if not isinstance(merged_errors, Mapping):
            raise TypeError("merged_errors must be a mapping")

        if not isinstance(direct_units_response, Mapping):
            raise TypeError("direct_units_response must be a mapping")

        if not isinstance(direct_units_errors, list):
            raise TypeError("direct_units_errors must be a list")

        return cls(
            merged_response=MergeResponse.from_dict(merged_response),
            merged_errors=MergeErrors.from_dict(merged_errors),
            direct_units_response=DirectUnitsResponse.from_dict(
                direct_units_response
            ),
            direct_units_errors=direct_units_errors,
        )
