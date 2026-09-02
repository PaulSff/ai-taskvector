from __future__ import annotations

from dataclasses import asdict

from agents.chat.agent_workflow.wf_response_schema import (
    AgentWorkflowResponse,
    DirectUnitsResponse,
    MergeErrors,
    MergeResponse,
)
from agents.chat.context.llm_prompt_inspector import (
    attach_llm_prompt_debug_from_outputs,
)
from core.schemas.primitives import (
    WorkflowErrors,
    WorkflowOutputs,
    is_string_keyed_dict,
)

from .helpers import (
    get_data,
    get_graph,
    get_nested_data,
    get_optional_data,
    get_optional_parser_output,
    get_optional_str,
    get_str,
    get_units_response,
)


def collect_workflow_errors(
    outputs: WorkflowOutputs,
) -> WorkflowErrors:
    """
    Collect non-null error port values from workflow outputs.

    Returns:
        A list of ``(unit_id, error_message)`` tuples for units that emitted
        an error.
    """
    errors: WorkflowErrors = []

    if not is_string_keyed_dict(outputs):
        return errors

    for unit_id, unit_out in outputs.items():
        if not is_string_keyed_dict(unit_out):
            continue

        err = unit_out.get("error")

        if isinstance(err, str) and err.strip():
            errors.append((unit_id, err.strip()))

    return errors

def _build_merge_errors(outputs: WorkflowOutputs) -> MergeErrors:
    merge_errors_data = get_nested_data(outputs, "merge_errors")

    return MergeErrors(
        llm_agent=get_str(merge_errors_data, "llm_agent"),
        parser=get_str(merge_errors_data, "parser"),
        process=get_str(merge_errors_data, "process"),
        run_workflow=get_str(merge_errors_data, "run_workflow"),
        report=get_str(merge_errors_data, "report"),
        grep=get_str(merge_errors_data, "grep"),
        delegate_request=get_str(
            merge_errors_data,
            "delegate_request",
        ),
    )

def _build_direct_units_response(
    outputs: WorkflowOutputs,
) -> DirectUnitsResponse:
    return DirectUnitsResponse(
        llm_prompt=get_optional_str(outputs, "llm_prompt"),
        llm_prompt_debug=get_optional_data(
            outputs,
            "llm_prompt_debug",
        ),
        parser_output=get_optional_parser_output(
            outputs,
            "parser_output",
        ),
        run_output=get_data(outputs, "run_output"),
        report_output=get_data(outputs, "report_output"),
        grep_output=get_data(outputs, "grep_output"),
        formulas_calc_output=get_data(
            outputs,
            "formulas_calc_output",
        ),
        formulas_calc_error=get_str(
            outputs,
            "formulas_calc_error",
        ),
        delegate_request=get_data(
            outputs,
            "delegate_request",
        ),
        delegate_request_error=get_str(
            outputs,
            "delegate_request_error",
        ),
        units_response=get_units_response(outputs),
    )


def merge_response_from_workflow_outputs(
    outputs: WorkflowOutputs,
) -> AgentWorkflowResponse:
    """Shape raw run_workflow unit outputs into run_agent_workflow response dict - AgentWorkflowResponse.

Workflow response:

    outputs (workflow outputs)
    ├── merge_response (output of the merge_response final unit)
    │   └── data
    │       ├── reply
    │       ├── result
    │       ├── status  (workflow status)
    │       ├── graph  (current: ProcessGraph)
    │       ├── diff  (ProcessGraph difference prev/current)
    │       ├── workflow_errors (aggregated errors form units)
    │       ├── parser_output  (LLM actions parser output)
    │       ├── run_output (inline tool output)
    │       ├── report_output (inline tool output)
    │       ├── grep_output (inline tool output)
    │       ├── formulas_calc_output (inline tool output)
    │       ├── formulas_calc_error (inline tool output)
    │       ├── delegate_request (inline tool output)
    │       ├── delegate_request_error (inline tool output)
    │       └── other inline tools outputs
    │
    ├── merge_errors (output of the merge_errors final unit)
    │   └── data
    │       ├── llm_agent
    │       ├── parser
    │       ├── process
    │       ├── run_workflow
    │       ├── report
    │       ├── grep
    │       └── delegate_request
    │
    ├── parser_output
    ├── run_output
    ├── grep_output
    ├── formulas_calc_output
    ├── formulas_calc_output
    └── ...

 The function output:

    outputs
    ├── merge_response.data  ──► MergeResponse
    ├── merge_errors.data    ──► MergeErrors
    ├── direct unit response  ──►  DirectUnitsResponse (intermediate workflow data)
    └── direct unit errors  ──► WorkflowErrors (intermediate workflow errors from each unit)

The processing order is therefore:
    1. Extract merge_response.data
    2. Apply defaults
    3. Apply reply fallback from llm_agent
    4. Collect workflow errors
    5. Attach LLM prompt debugging data
    6. Build AgentWorkflowResponse

    """
    workflow_errors = collect_workflow_errors(outputs)

    merge_response_data = get_nested_data(outputs, "merge_response")

    merged_response = MergeResponse(
        reply=get_str(merge_response_data, "reply"),
        result=get_data(merge_response_data, "result"),
        status=get_data(merge_response_data, "status"),
        graph=get_graph(merge_response_data, "graph"),
        diff=get_str(merge_response_data, "diff"),
        workflow_errors=workflow_errors,
        parser_output=get_optional_parser_output(
            merge_response_data,
            "parser_output",
        ),
        run_output=get_data(
            merge_response_data,
            "run_output",
        ),
        report_output=get_data(
            merge_response_data,
            "report_output",
        ),
        grep_output=get_data(
            merge_response_data,
            "grep_output",
        ),
        formulas_calc_output=get_data(
            merge_response_data,
            "formulas_calc_output",
        ),
        formulas_calc_error=get_str(
            merge_response_data,
            "formulas_calc_error",
        ),
        delegate_request=get_data(
            merge_response_data,
            "delegate_request",
        ),
        delegate_request_error=get_str(
            merge_response_data,
            "delegate_request_error",
        ),
    )

    if not merged_response.reply.strip():
        llm_agent = outputs.get("llm_agent")

        if is_string_keyed_dict(llm_agent):
            action = llm_agent.get("action")

            if isinstance(action, str) and action.strip():
                merged_response.reply = action.strip()

    merged_response_data = asdict(merged_response)

    attach_llm_prompt_debug_from_outputs(
        outputs,
        merged_response_data,
    )

    merged_response = MergeResponse.from_dict(merged_response_data)

    return AgentWorkflowResponse(
        merged_response=merged_response,
        merged_errors=_build_merge_errors(outputs),
        direct_units_response=_build_direct_units_response(outputs),
        direct_units_errors=workflow_errors,
    )
