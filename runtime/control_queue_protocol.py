from typing import Literal, Protocol, TypedDict

from core.schemas.primitives import (
    JsonObject,
)


class ProcessQueue(Protocol):
    def put(self, item: JsonObject) -> None:
        ...

class StopWorkflowRequest(TypedDict):
    action: Literal["stop_workflow"]
    run_id: str

class ControlQueue(Protocol):
    def get_nowait(self) -> StopWorkflowRequest:
        ...

    def put(
        self,
        obj: StopWorkflowRequest,
        block: bool = True,
        timeout: float | None = None,
    ) -> None:
        ...

    def close(self) -> None:
        ...

    def join_thread(self) -> None:
        ...
