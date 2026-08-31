from __future__ import annotations

from typing import Literal, NotRequired, Protocol, TypedDict

from pydantic import BaseModel

from core.schemas.graph_edit_api import MultipleEditsSequential
from core.schemas.process_graph import ProcessGraph

DiffFormat = Literal["str", "array", "payload"]


class UnitDiff(TypedDict):
    id: str
    type: str


class ConnectionDiff(TypedDict):
    from_: str
    to: str
    from_port: str
    to_port: str
    connection_type: str

class TodoListDiff(TypedDict):
    id: str
    title_changed: NotRequired[str]
    tasks_added: NotRequired[list[str]]
    tasks_removed: NotRequired[list[str]]
    tasks_updated: NotRequired[list[str]]

class GraphDiffPayload(TypedDict):
    environment_type_changed: bool
    environments_changed: bool
    keep_alive_changed: bool

    units_added: list[UnitDiff]
    units_removed: list[str]
    units_updated: list[str]

    connections_added: list[dict[str, object]]
    connections_removed: list[dict[str, object]]

    code_blocks_added: list[str]
    code_blocks_removed: list[str]
    code_blocks_updated: list[str]

    layout_changed: bool

    comments_added: list[str]
    comments_removed: list[str]
    comments_updated: list[str]

    origin_changed: bool

    todo_lists_added: list[str]
    todo_lists_removed: list[str]
    todo_lists_updated: list[TodoListDiff]

    tabs_added: list[str]
    tabs_removed: list[str]
    tab_meta_changed: list[str]
    tabs: dict[str, object]

    metadata_changed: bool

class MergeResult(BaseModel):
    multiple_edits_sequential: MultipleEditsSequential
    success: bool
    graph: ProcessGraph
    error: str | None = None


class GraphDiffFunction(Protocol):
    def __call__(
        self,
        prev: ProcessGraph | None,
        current: ProcessGraph | None,
        *,
        format: DiffFormat,
    ) -> str | list[str] | GraphDiffPayload:
        ...
