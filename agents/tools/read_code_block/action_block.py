
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents.tools.read_code_block import run_read_code_block_follow_up
from agents.tools.registry import register_tool
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


def register_read_code_tool() -> None:
    register_tool(
        "read_code_block",
        run_read_code_block_follow_up,
        action_blocks={
            "read_code_block": ReadCodeActionBlock,
        },
        action_handlers={
            "read_code_block": handle_read_code,
        },
    )


register_read_code_tool()
