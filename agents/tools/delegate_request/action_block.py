# agents/tools/action_blocks/delegate_request.py

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from agents.tools.registry import register_action_block
from agents.tools.types import ActionBlock, ParsedActions


class DelegateRequestParserOutput(BaseModel):
    """Normalized delegate-request action stored in ParsedActions."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["delegate_request"]
    delegate_to: str
    message: str

    @field_validator("delegate_to", "message")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("value must not be empty")

        return value


class DelegateRequestActionBlock(
    ActionBlock[Literal["delegate_request"]]
):
    """Delegate the current request to another role."""

    delegate_to: str
    message: str

    @field_validator("delegate_to", "message")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
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


def register_delegate_request_action_blocks() -> None:
    register_action_block(
        "delegate_request",
        DelegateRequestActionBlock,
        handler=handle_delegate_request,
    )


def get_delegate_request_outputs(
    actions: ParsedActions,
) -> list[DelegateRequestParserOutput]:
    return [
        DelegateRequestParserOutput.model_validate(raw_action)
        for raw_action in actions.get_tool_actions("delegate_request")
    ]
