"""
Shared types for agent follow-up tools.

Tool runners consume normalized parser output and a narrow follow-up context protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    model_validator,
)

from core.schemas.graph_edit_api import GraphEdit
from core.schemas.primitives import Data

# Keys for ``FollowUpContribution.extra`` merged by the Workflow Designer orchestrator.
FOLLOW_UP_EXTRA_READ_CODE_IDS = "read_code_ids_for_msg"
FOLLOW_UP_EXTRA_IMPLEMENTATION_LINK_TYPES = "implementation_links_for_types"
FOLLOW_UP_EXTRA_REPORT_FOLLOW_UP = "report_follow_up"
FOLLOW_UP_EXTRA_FORMULAS_CALC_FOLLOW_UP = "formulas_calc_follow_up"
FOLLOW_UP_EXTRA_CALENDAR_FOLLOW_UP = "calendar_follow_up"
FOLLOW_UP_EXTRA_CLONE_ROLE_FOLLOW_UP = "clone_role_follow_up"
FOLLOW_UP_EXTRA_LIST_DIR_FOLLOW_UP = "list_dir_follow_up"
FOLLOW_UP_EXTRA_READ_FILE_FOLLOW_UP = "read_file_follow_up"

type ToolList = tuple[str, ...]


class ActionBlock(BaseModel):
    """
    An LLM-emitted action with the shape:

        {
            "action": "<parser_key>",
            ...
        }

    The action must be either:

    - a parser_key belonging to one of the registered tool runners; or
    - a valid GraphEdit action.
    """

    model_config = ConfigDict(
        extra="allow",
        strict=True,
    )

    action: str

    @staticmethod
    @cache
    def _valid_parser_keys() -> frozenset[str]:
        # Import lazily to avoid a circular import if the tool-runner module
        # imports ActionBlock.
        from .catalog import parser_keys_for_tool
        from .registry import TOOL_RUNNERS

        parser_keys: set[str] = set()

        for tool_id in TOOL_RUNNERS:
            keys = parser_keys_for_tool(tool_id)

            if keys is not None:
                parser_keys.update(keys)

        return frozenset(parser_keys)

    @model_validator(mode="after")
    def validate_action(self) -> ActionBlock:
        if self.action in self._valid_parser_keys():
            return self

        if self.is_edit:
            return self

        raise ValueError(
            f"Invalid action {self.action!r}; expected a parser_key from "
            "a registered tool runner or a valid GraphEdit action"
        )

    @property
    def is_edit(self) -> bool:
        """Whether the complete action is a valid GraphEdit."""

        raw_action: Data = {
            "action": self.action,
            **(self.model_extra or {}),
        }

        try:
            GraphEdit.model_validate(raw_action)
        except ValidationError:
            return False

        return True

    def as_json_object(self) -> Data:
        return self.model_dump(mode="json")


@dataclass
class FollowUpContribution:
    """Result of running one tool in a follow-up round."""

    context_chunks: list[str] = field(default_factory=list)
    any_empty_tool: bool = False
    extra: dict[str, object] = field(default_factory=dict)


@dataclass
class ParsedActions:
    # GraphEdits calls
    edits: list[GraphEdit] = field(default_factory=list)
    # Tool calls
    read_file: list[str] = field(default_factory=list)
    read_code_block_ids: list[str] = field(default_factory=list)
    read_current_workflow: bool = False

    web_search: str | None = None
    web_search_max_results: int | None = None
    browse_url: str | None = None

    github: Data | None = None
    report: Data | None = None
    run_workflow: Data | None = None
    grep: Data | None = None
    formulas_calc: Data | None = None
    delegate_request: Data | None = None

    send_message: list[Data] = field(default_factory=list)
    get_unread: list[Data] = field(default_factory=list)

    calendar: Data | None = None
    clone_role: Data | None = None
    rag_search: Data | None = None
    list_dir: Data | None = None
    new_file: Data | None = None
    edit_file: Data | None = None
    rename: Data | None = None
    delete: Data | None = None
    make_dir: Data | None = None
    no_edit: Data | None = None


@dataclass
class ParserOutput:
    """The Output of the ProcessAgent Unit collecting the actions emitted by LLM within the role workflow"""
    actions: ParsedActions = field(default_factory=ParsedActions)
    error: str | None = None
