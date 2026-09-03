
from typing import Literal

from pydantic import BaseModel, ConfigDict

from agents.tools.types import ActionBlock

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
