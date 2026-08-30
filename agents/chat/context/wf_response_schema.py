from typing import TypedDict


class WorkflowError(TypedDict, total=False):
    message: str
    code: str


class ResponseData(TypedDict, total=False):
    result: dict[str, object]
    status: dict[str, object] | None
    workflow_errors: list[WorkflowError]
