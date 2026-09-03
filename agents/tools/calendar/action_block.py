from __future__ import annotations

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents.tools.types import ActionBlock


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
