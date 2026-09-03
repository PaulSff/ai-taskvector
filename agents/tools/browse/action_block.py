from typing import Literal

from agents.tools.types import ActionBlock


class BrowseActionBlock(ActionBlock[Literal["browse"]]):
    """Read a web page from an HTML or URL source."""

    url: str
