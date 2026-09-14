from __future__ import annotations

from typing import ClassVar, Literal, TypeGuard

from pydantic import BaseModel, ConfigDict, Field, computed_field

from core.schemas import NodePosition, ProcessGraph
from core.schemas.primitives import JsonValue, is_object_list

# Action types
GraphEditAction = Literal[
    "add_unit",
    "add_pipeline",
    "remove_unit",
    "set_params",
    "connect",
    "disconnect",
    "replace_graph",
    "replace_unit",
    "add_code_block",
    "add_comment",
    "remove_comment",
    "add_todo_list",
    "remove_todo_list",
    "add_task",
    "remove_task",
    "set_implementer",
    "set_deadline",
    "set_curator",
    "set_todo_list_title",
    "mark_completed",
    "add_environment",
    "import_workflow",
]

class FindUnit(BaseModel):
    """Unit selector for replace_unit (unit to find and remove)."""

    id: str = Field(..., description="Unit id to find and replace")


class GraphEditCodeBlock(BaseModel):
    """Code block payload for add_code_block (id = unit_id; one block per unit)."""

    id: str = Field(..., description="Unit id this code block belongs to")
    language: str = Field(
        ..., description="Language: javascript (Node-RED/n8n), python (PyFlow/Ryven)"
    )
    source: str = Field(default="", description="Raw source code")


class GraphEditUnit(BaseModel):
    """Unit payload for add_unit: a single graph unit (Source, Valve, Tank, Sensor, RLAgent, LLMAgent, etc.)."""

    id: str = Field(..., description="Unique unit identifier")
    type: str = Field(
        ...,
        description="Unit type: Source, Valve, Tank, Sensor, RLAgent, LLMAgent, etc.",
    )
    controllable: bool = Field(
        default=False, description="Whether this unit is an action/control input"
    )
    params: dict[str, JsonValue] = Field(
        default_factory=dict, description="Type-specific parameters"
    )
    name: str | None = Field(
        default=None, description="Optional display name for the unit"
    )


class GraphEditPipeline(BaseModel):
    """Pipeline payload for add_pipeline: RLGym, RLOracle, RLSet, or LLMSet (training/serving pipeline, not a single unit)."""

    id: str = Field(
        ...,
        description="Unique pipeline identifier (e.g. rl_training, ai_student, my_rl_agent, my_llm_agent)",
    )
    type: str = Field(
        ..., description="Pipeline type: RLGym, RLOracle, RLSet, or LLMSet"
    )
    params: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="observation_source_ids, action_target_ids, adapter_config, max_steps (RLGym/RLOracle); inference_url, model_path (RLSet); model_name, provider, system_prompt (LLMSet), etc.",
    )

class GraphEdit(BaseModel):
    """Structured graph edit from Process agent (validate in backend)."""

    action: GraphEditAction = Field(
        ...,
        description=(
                    "add_unit | add_pipeline | remove_unit | set_params | connect | disconnect | "
                    "replace_graph | replace_unit | add_code_block | add_comment | add_todo_list | "
                    "remove_todo_list | add_task | remove_task | mark_completed | set_implementer | "
                    "set_deadline | set_curator | add_environment | import_workflow"
                ),
            )
    unit_id: str | None = Field(default=None, description="For remove_unit")
    id: str | None = Field(
        default=None, description="For set_params: unit id to update"
    )
    new_params: dict[str, JsonValue] | None = Field(
        default=None,
        description="For set_params: params to set (merged into unit params)",
    )
    unit: GraphEditUnit | None = Field(
        default=None,
        description="For add_unit: single graph unit (process, RLAgent, LLMAgent)",
    )
    pipeline: GraphEditPipeline | None = Field(
        default=None,
        description="For add_pipeline: RLGym or RLOracle pipeline (not a unit)",
    )
    code_block: GraphEditCodeBlock | None = Field(
        default=None, description="For add_code_block"
    )
    code_blocks: list[GraphEditCodeBlock] | None = None
    find_unit: FindUnit | None = Field(
        default=None, description="For replace_unit: unit to find"
    )
    replace_with: GraphEditUnit | None = Field(
        default=None, description="For replace_unit: new unit"
    )
    from_id: str | None = Field(
        default=None, alias="from", description="Source unit id for connect/disconnect"
    )
    to_id: str | None = Field(
        default=None, alias="to", description="Target unit id for connect/disconnect"
    )
    from_port: str | None = Field(
        default=None, description="Source output port index for connect (default '0')"
    )
    to_port: str | None = Field(
        default=None, description="Target input port index for connect (default '0')"
    )
    units: list[dict[str, JsonValue]] | None = Field(
        default=None, description="For replace_graph: full unit list"
    )
    connections: list[dict[str, str]] | None = Field(
        default=None, description="For replace_graph: full connection list"
    )
    # import_workflow: source = file path or URL
    source: str | None = Field(
        default=None, description="For import_workflow: file path or URL"
    )
    merge: bool = Field(
        default=False,
        description="For import_workflow: merge into current graph instead of replace",
    )
    # add_comment/remove_comment: agent note on the flow (stored in graph comments metadata; not exported to external runtimes)
    info: str | None = Field(default=None, description="For add_comment: comment text")
    commenter: str | None = Field(
        default=None,
        description="For add_comment: optional identifier of who left the comment (e.g. agent name)",
    )
    comment_id: str | None = Field(
            default=None,
            description="For remove_comment: id of the comment to remove",
        )
    # Todo list actions (graph metadata; not exported to runtimes)
    x: float | None = Field(default=None, description="X coordinate for todo list/task")
    y: float | None = Field(default=None, description="Y coordinate for todo list/task")
    title: str | None = Field(
        default=None, description="For add_todo_list: optional list title"
    )
    task_id: str | None = Field(
        default=None, description="For remove_task, mark_completed: task id"
    )
    text: str | None = Field(default=None, description="For add_task: task description")
    completed: bool = Field(
        default=True, description="For mark_completed: set completed (default true)"
    )
    # add_environment: add an environment to the graph so env-specific units become available in the Units Library
    env_id: str | None = Field(
        default=None,
        description="For add_environment: environment id (e.g. thermodynamic, data_bi)",
    )
    todo_list_id: str | None = Field(
        default=None,
        description="For add_task, remove_task, mark_completed: target todo list id (required when multiple todo lists exist).",
    )
    implementer: str | None = Field(
            default=None,
            description="For set_implementer: task implementer (optional; set null to clear).",
        )
    deadline: str | None = Field(
        default=None,
        description="For set_deadline: task deadline (optional; set null to clear).",
    )
    curator: str | None = Field(
        default=None,
        description="For set_curator: task curator (optional; set null to clear).",
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(
            populate_by_name=True,
        )
    origin: str | None = None
    format: str | None = None
    layout: dict[str, NodePosition] | None = Field(
        default=None,
        description=(
            "For replace_graph: per-unit visual positions "
            "(unit_id -> {x, y})"
        ),
    )

class MultipleEditsSequential(BaseModel):
    edits: list[GraphEdit] = Field(
        default_factory=list,
        description="Graph edits to apply sequentially",
    )


class ApplyWorkflowEditsStatus(BaseModel):
    """
    Compact graph edit status.
    (returned through the status output port by the ApplyEdits Unit).
    """

    attempted: bool
    success: bool | None = None
    error: str | None = None
    edits_summary: str | None = None


class ApplyWorkflowEditsResult(BaseModel):
    """
    Detailed record of the most recent workflow-edit operation.

    (also corresponds to result["last_apply_result"] at the ApplyEdits Unit)
    """

    attempted: bool
    success: bool
    error: str | None = None

    graph_after: ProcessGraph = Field(
        description=(
            "Complete canonical process graph after the edit attempt. "
            "None when application was not attempted."
        ),
    )

    edits_summary: str | None = None



class AgentApplyWorkflowEditsResult(BaseModel):
    """
    Result payload of an Agent workflow edit attempt
    (also passed through the ApplyEdits Unit result output port).
    """

    kind: Literal["no_edits", "applied", "apply_failed"]

    content_for_display: str = Field(
        default="",
        description="Human-readable content for display.",
    )

    graph: ProcessGraph = Field(
        ...,
        description="Current canonical process graph.",
    )

    edits: list[GraphEdit] = Field(
        default_factory=list,
        description="Parsed and validated graph edits the graph was attempted to modify with.",
    )

    error_reason: str | None = Field(
        default=None,
        description=(
            "Reason edit extraction, graph loading, or edit validation failed."
        ),
    )

    last_apply_result: ApplyWorkflowEditsResult | None = Field(
        default=None,
        description=(
            "Details of the most recent workflow-edit operation. "
            "Absent when no edits were provided."
        ),
    )

    @computed_field
    @property
    def success(self) -> bool:
        result = self.last_apply_result
        return result.success if result is not None else False

    @computed_field
    @property
    def graph_after(self) -> ProcessGraph:
        result = self.last_apply_result
        return result.graph_after if result is not None else self.graph

    @computed_field
    @property
    def error(self) -> str | None:
        result = self.last_apply_result
        if result is not None:
            return result.error

        return self.error_reason


# helpers
def is_graph_edit(value: object) -> TypeGuard[GraphEdit]:
    return isinstance(value, GraphEdit)


def is_graph_edit_list(
    value: object,
) -> TypeGuard[list[GraphEdit]]:
    if not is_object_list(value):
        return False

    return all(is_graph_edit(item) for item in value)


IMPORT_WORKFLOW_ACTION: GraphEditAction = "import_workflow"
COMMENT_ACTIONS: frozenset[GraphEditAction] = frozenset(
    {
        "add_comment",
        "remove_comment"
    }
)
TODO_ACTIONS: frozenset[GraphEditAction] = frozenset(
    {
        "add_todo_list",
        "remove_todo_list",
        "add_task",
        "remove_task",
        "mark_completed",
    }
)
