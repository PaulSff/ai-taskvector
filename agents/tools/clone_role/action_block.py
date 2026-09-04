# clone_role/action_blocks.py

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents.tools.registry import register_action_block
from agents.tools.types import ActionBlock, ParsedActions


class CloneRoleFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_role_name: str
    character_name: str
    responsibility: str
    intro_brief: str
    prompt_duties: str
    prompt_conversational_behavior: str
    prompt_reasoning: str
    tools: list[str] = Field(default_factory=list)


class CloneRoleParserOutput(CloneRoleFields):
    """Normalized clone-role action stored in ParsedActions."""

    action: Literal["clone_role"]


class CloneRoleActionBlock(
    ActionBlock[Literal["clone_role"]],
    CloneRoleFields,
):
    """Create a new role by cloning an existing role."""


def handle_clone_role(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, CloneRoleActionBlock):
        raise TypeError(
            f"Expected CloneRoleActionBlock, got {type(block).__name__}"
        )

    actions.add_tool_action(
        "clone_role",
        block.as_json_object(),
    )


def register_clone_role_action_blocks() -> None:
    register_action_block(
        "clone_role",
        CloneRoleActionBlock,
        handler=handle_clone_role,
    )
