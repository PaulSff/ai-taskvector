from typing import Literal

from agents.tools.types import ActionBlock


class AddCommentActionBlock(ActionBlock[Literal["add_comment"]]):
    info: str


class RemoveCommentActionBlock(ActionBlock[Literal["remove_comment"]]):
    comment_id: str
