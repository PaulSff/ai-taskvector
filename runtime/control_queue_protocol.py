from typing import Any, Literal, Protocol, TypeAlias

FormatProcess = Literal[
    "yaml",
    "dict",
    "node_red",
    "template",
    "pyflow",
]

JsonValue: TypeAlias = ( # noqa: UP040
    str
    | int
    | float
    | bool
    | None
    | list["JsonValue"]
    | dict[str, "JsonValue"]
)

JsonObject: TypeAlias = dict[str, JsonValue] # noqa: UP040
WorkflowInputs: TypeAlias = dict[str, dict[str, object]]  # noqa: UP040

class ProcessQueue(Protocol):
    def put(self, item: JsonObject) -> None:
        ...

class ControlQueue(Protocol):
    def get_nowait(self) -> object:
        ...

    def put(
        self,
        obj: Any,
        block: bool = True,
        timeout: float | None = None,
    ) -> None:
        ...

    def close(self) -> None:
        ...

    def join_thread(self) -> None:
        ...
