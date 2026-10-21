from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from agents.tools.air_shopping_rq import run_air_shopping_rq_follow_up
from agents.tools.registry import register_tool
from agents.tools.types import ParsedActions
from core.schemas.primitives import Data


class AirShoppingRQMethodBlock(BaseModel):
    AirShoppingRQ: Data


class AirShoppingRQActionBlock(BaseModel):
    action: Literal["get_low_fare_flight_calendar"]
    method: AirShoppingRQMethodBlock

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        if value != "get_low_fare_flight_calendar":
            raise ValueError(
                'action must be "get_low_fare_flight_calendar"'
            )
        return value


def handle_air_shopping_rq(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, AirShoppingRQActionBlock):
        raise TypeError(
            "Expected an air_shopping_rq action block, "
            f"got {type(block).__name__}"
        )

    actions.add_tool_action(
        "air_shopping_rq",
        block.model_dump(mode="json"),
    )


def register_air_shopping_rq_tool() -> None:
    register_tool(
        "air_shopping_rq",
        run_air_shopping_rq_follow_up,
        action_blocks={
            "air_shopping_rq": AirShoppingRQActionBlock,
        },
        action_handlers={
            "air_shopping_rq": handle_air_shopping_rq,
        },
    )


register_air_shopping_rq_tool()
