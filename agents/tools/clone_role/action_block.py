from typing import Literal

from agents.tools.types import ActionBlock


class CloneRoleActionBlock(ActionBlock[Literal["clone_role"]]):
    """Create a new role by cloning an existing role."""

    new_role_name: str
    character_name: str
    responsibility: str
    intro_brief: str
    prompt_duties: str
    prompt_conversational_behavior: str
    prompt_reasoning: str
    tools: list[str]
