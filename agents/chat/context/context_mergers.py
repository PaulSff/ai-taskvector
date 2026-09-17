from __future__ import annotations

from dataclasses import replace

from agents.chat.agent_workflow.wf_response_schema import AgentWorkflowResponse
from agents.chat.context.follow_up_context import WDFollowUpAcc
from agents.tools.types import (
    FOLLOW_UP_EXTRA_CALENDAR_FOLLOW_UP,
    FOLLOW_UP_EXTRA_CLONE_ROLE_FOLLOW_UP,
    FOLLOW_UP_EXTRA_FORMULAS_CALC_FOLLOW_UP,
    FOLLOW_UP_EXTRA_IMPLEMENTATION_LINK_TYPES,
    FOLLOW_UP_EXTRA_LIST_DIR_FOLLOW_UP,
    FOLLOW_UP_EXTRA_READ_CODE_IDS,
    FOLLOW_UP_EXTRA_READ_FILE_FOLLOW_UP,
    FOLLOW_UP_EXTRA_REPORT_FOLLOW_UP,
    FollowUpContribution,
)
from core.schemas.primitives import is_object_list


def merge_preserved_apply_failure_into_response(
    response: AgentWorkflowResponse,
    preserved: AgentWorkflowResponse,
) -> AgentWorkflowResponse:
    response_merge = response.merged_response
    preserved_merge = preserved.merged_response

    merged_errors = list(response_merge.workflow_errors)

    for error in preserved_merge.workflow_errors:
        if error not in merged_errors:
            merged_errors.append(error)

    merged_response = replace(
        response_merge,
        result=preserved_merge.result,
        status=preserved_merge.status,
        workflow_errors=merged_errors,
    )

    return replace(response, merged_response=merged_response)


def merge_follow_up_contribution_into_acc(
    acc: WDFollowUpAcc,
    contrib: FollowUpContribution,
) -> None:
    acc.context_chunks.extend(contrib.context_chunks)

    if contrib.any_empty_tool:
        acc.any_empty_tool = True

    ex = contrib.extra

    v = ex.get(FOLLOW_UP_EXTRA_READ_CODE_IDS)
    if is_object_list(v):
        acc.read_code_ids_for_msg = [str(x) for x in v]

    v = ex.get(FOLLOW_UP_EXTRA_IMPLEMENTATION_LINK_TYPES)
    if is_object_list(v):
        acc.implementation_links_for_types = [str(x) for x in v]

    if ex.get(FOLLOW_UP_EXTRA_REPORT_FOLLOW_UP):
        acc.report_follow_up = True

    if ex.get(FOLLOW_UP_EXTRA_FORMULAS_CALC_FOLLOW_UP):
        acc.formulas_calc_follow_up = True

    if ex.get(FOLLOW_UP_EXTRA_CALENDAR_FOLLOW_UP):
        acc.calendar_follow_up = True

    if ex.get(FOLLOW_UP_EXTRA_CLONE_ROLE_FOLLOW_UP):
        acc.clone_role_follow_up = True

    if ex.get(FOLLOW_UP_EXTRA_LIST_DIR_FOLLOW_UP):
        acc.list_dir_follow_up = True

    if ex.get(FOLLOW_UP_EXTRA_READ_FILE_FOLLOW_UP):
        acc.read_file_follow_up = True
_follow_up = True
