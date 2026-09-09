from __future__ import annotations

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents.tools.calendar import run_calendar_follow_up
from agents.tools.registry import register_tool
from agents.tools.types import ActionBlock, ParsedActions


class CalendarDateTime(BaseModel):
    """A calendar date and time."""

    model_config = ConfigDict(
        extra="allow",
        strict=True,
    )

    date: date
    time: time


class PeriodicAvailability(BaseModel):
    """A recurring weekly availability period."""

    model_config = ConfigDict(
        extra="allow",
        strict=True,
    )

    periodic: dict[str, str]


class GetAllCalendarsActionBlock(ActionBlock[Literal["calendar"]]):
    method: Literal["get_all_calendars"]


class CheckAvailabilityActionBlock(ActionBlock[Literal["calendar"]]):
    method: Literal["check_availability"]
    cal_file_name: str
    period_d: int
    include_scheduled_events: bool
    availability: list[PeriodicAvailability]


class ReserveActionBlock(ActionBlock[Literal["calendar"]]):
    method: Literal["reserve"]
    cal_file_name: str
    from_: CalendarDateTime = Field(alias="from")
    to: CalendarDateTime
    event_name: str


class CancelActionBlock(ActionBlock[Literal["calendar"]]):
    method: Literal["cancel"]
    cal_file_name: str
    event_id: str


CalendarActionBlock = (
    GetAllCalendarsActionBlock
    | CheckAvailabilityActionBlock
    | ReserveActionBlock
    | CancelActionBlock
)


_CALENDAR_ACTION_BLOCK_TYPES = (
    GetAllCalendarsActionBlock,
    CheckAvailabilityActionBlock,
    ReserveActionBlock,
    CancelActionBlock,
)


def handle_calendar(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, _CALENDAR_ACTION_BLOCK_TYPES):
        raise TypeError(
            f"Expected a calendar action block, got {type(block).__name__}"
        )

    actions.add_tool_action(
        "calendar",
        block.as_json_object(),
    )


def register_calendar_tool() -> None:
    register_tool(
        "calendar",
        run_calendar_follow_up,
        action_blocks={
            "calendar": _CALENDAR_ACTION_BLOCK_TYPES,
        },
        action_handlers={
            "calendar": handle_calendar,
        },
    )


register_calendar_tool()
