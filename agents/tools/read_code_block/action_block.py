
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents.tools.registry import register_action_block
from agents.tools.types import ActionBlock, ParsedActions


class ReadCodeBlockParserOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code_block_ids: list[str] = Field(default_factory=list)


class ReadCodeActionBlock(ActionBlock[Literal["read_code_block"]]):
    code_block_ids: list[str]


def handle_read_code(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, ReadCodeActionBlock):
        raise TypeError(
            f"Expected ReadCodeActionBlock, got {type(block).__name__}"
        )

    actions.add_tool_action(
        "read_code_block",
        block.as_json_object(),
    )


def register_read_code_action_blocks() -> None:
    register_action_block(
        "read_code_block",
        ReadCodeActionBlock,
        handler=handle_read_code,
    )
