"""Web search unit: DuckDuckGo query → plain text results."""
from units.web.web_search.web_search import (
    WEB_SEARCH_INPUT_PORTS,
    WEB_SEARCH_OUTPUT_PORTS,
    run_web_search,
    register_web_search,
)

__all__ = ["register_web_search", "run_web_search", "WEB_SEARCH_INPUT_PORTS", "WEB_SEARCH_OUTPUT_PORTS"]
