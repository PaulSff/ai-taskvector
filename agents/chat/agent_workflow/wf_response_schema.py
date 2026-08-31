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
from typing import Self

from core.schemas.primitives import Data, WorkflowErrors
from core.schemas.process_graph import ProcessGraph

# Units standard API:
#   Data = dict[str, object]
#   Output = tuple[Data, Data] | Data
#   WorkflowOutputs = JsonObject
#   WorkflowErrors = list[tuple[str, str]]

@dataclass
class MergeResponse:
    reply: str = ""
    result: Data = field(default_factory=dict)
    status: Data = field(default_factory=dict)
    graph: ProcessGraph | None = None
    diff: str = ""

    workflow_errors: WorkflowErrors = field(default_factory=list)

    llm_prompt: str | None = None
    llm_prompt_debug: Data | None = None
    llm_system_prompt: str | None = None
    llm_user_message: str | None = None

    parser_output: Data | None = None
    run_output: Data = field(default_factory=dict)
    report_output: Data = field(default_factory=dict)
    grep_output: Data = field(default_factory=dict)

    formulas_calc_output: Data = field(default_factory=dict)
    formulas_calc_error: str = ""

    delegate_request: Data = field(default_factory=dict)
    delegate_request_error: str = ""

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


@dataclass
class MergeErrors:
    """Contents of outputs['merge_errors']['data']."""

    llm_agent: str = ""
    parser: str = ""
    process: str = ""
    run_workflow: str = ""
    report: str = ""
    grep: str = ""
    delegate_request: str = ""

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


@dataclass
class DirectUnitsResponse:
    """Direct unit outputs before the final merge units run."""

    llm_prompt: str | None = None
    llm_prompt_debug: Data | None = None

    parser_output: Data | None = None
    run_output: Data = field(default_factory=dict)
    report_output: Data = field(default_factory=dict)
    grep_output: Data = field(default_factory=dict)

    formulas_calc_output: Data = field(default_factory=dict)
    formulas_calc_error: str = ""

    delegate_request: Data = field(default_factory=dict)
    delegate_request_error: str = ""

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


@dataclass
class AgentWorkflowResponse:
    """Final response returned by run_agent_workflow."""

    merged_response: MergeResponse = field(default_factory=MergeResponse)
    merged_errors: MergeErrors = field(default_factory=MergeErrors)
    direct_units_response: DirectUnitsResponse = field(
        default_factory=DirectUnitsResponse
    )
    direct_units_errors: WorkflowErrors = field(default_factory=list)
