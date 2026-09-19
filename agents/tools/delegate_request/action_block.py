# agents/tools/action_blocks/delegate_request.py

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from agents.tools.delegate_request import run_delegate_request_follow_up
from agents.tools.registry import register_tool
from agents.tools.types import ActionBlock, ParsedActions


class DelegateRequestParserOutput(BaseModel):
    """Normalized delegate-request action stored in ParsedActions."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["delegate_request"]
    delegate_to: str | None = None
    message: str | None = None

    @field_validator("delegate_to", "message")
    @classmethod
    def validate_optional_non_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("value must not be empty")

        return value


class DelegateRequestActionBlock(
    ActionBlock[Literal["delegate_request"]]
):
    """Delegate the current request to another role."""

    model_config = ConfigDict(extra="forbid")

    delegate_to: str | None = None
    message: str | None = None

    @field_validator("delegate_to", "message")
    @classmethod
    def validate_optional_non_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("value must not be empty")

        return value


def handle_delegate_request(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, DelegateRequestActionBlock):
        raise TypeError(
            f"Expected DelegateRequestActionBlock, got {type(block).__name__}"
        )

    actions.add_tool_action(
        "delegate_request",
        block.as_json_object(),
    )


def register_delegate_request_tool() -> None:
    register_tool(
        "delegate_request",
        run_delegate_request_follow_up,
        action_blocks={
            "delegate_request": DelegateRequestActionBlock,
        },
        action_handlers={
            "delegate_request": handle_delegate_request,
        },
    )


def get_delegate_request_outputs(
    actions: ParsedActions,
) -> list[DelegateRequestParserOutput]:
    return [
        DelegateRequestParserOutput.model_validate(raw_action)
        for raw_action in actions.get_tool_actions("delegate_request")
    ]


register_delegate_request_tool()
