from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from agents.tools.registry import register_action_block
from agents.tools.types import ActionBlock, ParsedActions

GithubAction = Literal[
    "github_search_repos",
    "github_search_code",
    "github_search_issues",
    "github_get_repo",
    "github_get_content",
    "github_get_readme",
    "github_list_releases",
    "github_list_commits",
]


class GithubPayload(BaseModel):
    """Action-specific GitHub operation and its parameters."""

    model_config = ConfigDict(
        extra="allow",
        strict=True,
    )

    action: GithubAction


class GithubActionBlock(
    ActionBlock[Literal["github"]]
):
    """Query GitHub."""

    payload: GithubPayload


def handle_github(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, GithubActionBlock):
        raise TypeError(
            "Expected a github action block, "
            f"got {type(block).__name__}"
        )

    actions.add_tool_action(
        "github",
        block.as_json_object(),
    )


def register_github_action_blocks() -> None:
    register_action_block(
        "github",
        GithubActionBlock,
        handler=handle_github,
    )
