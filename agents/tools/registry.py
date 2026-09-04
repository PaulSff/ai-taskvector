"""
Generic tool and action-block registry.

Tool modules register themselves with register_tool():

    register_tool(
        "todo_manager",
        run_todo_manager_follow_up,
        action_blocks={
            "add_task": AddTaskActionBlock,
            "add_todo_list": AddTodoListActionBlock,
        },
    )
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ValidationError

from agents.tools.types import LanguageHintGetter, ParsedActions, ParserOutput, ToolList

if TYPE_CHECKING:
    from agents.chat.context.follow_up_context import ParserFollowUpContext
    from agents.tools.types import FollowUpContribution


type ActionBlockType = type[BaseModel]
type ActionBlockTypes = ActionBlockType | Iterable[ActionBlockType]
type ActionBlockHandler = Callable[[ParsedActions, BaseModel], None]


@dataclass(frozen=True)
class ActionRegistration:
    models: tuple[type[BaseModel], ...]
    handle: ActionBlockHandler | None = None


class FollowUpRunner(Protocol):
    def __call__(
        self,
        ctx: ParserFollowUpContext,
        po: ParserOutput,
        *,
        language_hint: LanguageHintGetter,
    ) -> Awaitable[FollowUpContribution]:
        ...


# Stable tool ID -> follow-up runner.
TOOL_RUNNERS: dict[str, FollowUpRunner] = {}

# Stable action ID -> action-block model candidates.
TOOL_ACTION_BLOCKS: dict[str, ActionRegistration] = {}


def _clear_parser_cache() -> None:
    """
    Invalidate parser caches after registry changes.

    The import is local to avoid a circular import during startup.
    """
    from .types import ActionBlock

    ActionBlock._valid_parser_keys.cache_clear()


def _normalize_action_blocks(
    action_blocks: ActionBlockTypes,
) -> tuple[ActionBlockType, ...]:
    if isinstance(action_blocks, type):
        result = (action_blocks,)
    else:
        result = tuple(action_blocks)

    if not result:
        raise ValueError("At least one action-block type is required")

    for action_block_type in result:
        if not isinstance(action_block_type, type):
            raise TypeError(
                "Action blocks must be Pydantic model classes"
            )

        if not issubclass(action_block_type, BaseModel):
            raise TypeError(
                "Action blocks must inherit from pydantic.BaseModel"
            )

    return result


def register_action_block(
    action: str,
    action_blocks: ActionBlockTypes,
    *,
    handler: ActionBlockHandler | None = None,
    append: bool = False,
) -> None:
    """
    Register one or more models for a parser action.

    This is mainly useful when an action is added after the tool has already
    been registered. Normal tool registration should use register_tool().
    """
    if not action:
        raise ValueError("action is required")

    normalized = _normalize_action_blocks(action_blocks)
    existing = TOOL_ACTION_BLOCKS.get(action)

    if append and existing is not None:
        models = (*existing.models, *normalized)

        # Preserve the existing handler unless a new one is supplied.
        effective_handler = (
            handler if handler is not None else existing.handle
        )
    else:
        models = normalized
        effective_handler = handler

    TOOL_ACTION_BLOCKS[action] = ActionRegistration(
        models=models,
        handle=effective_handler,
    )

    _clear_parser_cache()


def register_tool(
    tool_id: str,
    impl: FollowUpRunner,
    *,
    action_blocks: Mapping[str, ActionBlockTypes] | None = None,
) -> None:
    """
    Register a tool runner and all parser action blocks owned by that tool.

    A tool may expose multiple parser actions:

        register_tool(
            "todo_manager",
            run_todo_manager_follow_up,
            action_blocks={
                "add_task": AddTaskActionBlock,
                "add_todo_list": AddTodoListActionBlock,
            },
        )
    """
    tool_id = tool_id.strip()

    if not tool_id:
        raise ValueError("tool_id is required")

    TOOL_RUNNERS[tool_id] = impl

    for action, action_block_types in (action_blocks or {}).items():
        register_action_block(action, action_block_types)

    _clear_parser_cache()


def parse_action_block(raw_action: dict) -> BaseModel:
    """
    Validate and instantiate an action block using its action value.
    """
    action = raw_action.get("action")

    if not isinstance(action, str):
        raise TypeError("action must be a string")

    action = action.strip()

    registration = TOOL_ACTION_BLOCKS.get(action)

    if registration is None:
        raise ValueError(f"Unknown action: {action!r}")

    errors: list[ValidationError] = []

    for action_block_type in registration.models:
        try:
            return action_block_type.model_validate(raw_action)
        except ValidationError as error:
            errors.append(error)

    raise ValueError(
        f"Invalid payload for action {action!r}: "
        f"{len(errors)} candidate model(s) failed validation"
    ) from errors[-1]


def get_follow_up_runner(
    tool_id: str,
) -> FollowUpRunner | None:
    return TOOL_RUNNERS.get((tool_id or "").strip())


def get_action_block_types(
    action: str,
) -> tuple[ActionBlockType, ...]:
    registration = TOOL_ACTION_BLOCKS.get(action.strip())

    if registration is None:
        return ()

    return registration.models


def get_action_registration(
    action: str,
) -> ActionRegistration | None:
    return TOOL_ACTION_BLOCKS.get((action or "").strip())


def list_tool_ids() -> ToolList:
    return tuple(sorted(TOOL_RUNNERS))


def list_action_ids() -> tuple[str, ...]:
    return tuple(sorted(TOOL_ACTION_BLOCKS))


def clear_tool_registry() -> None:
    TOOL_RUNNERS.clear()
    TOOL_ACTION_BLOCKS.clear()
    _clear_parser_cache()
