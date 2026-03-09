"""Web environment units: browser, web_search. Python-only; not exported to Node-RED/PyFlow."""

from units.web.browser import register_browser, BROWSER_INPUT_PORTS, BROWSER_OUTPUT_PORTS
from units.web.web_search import register_web_search, WEB_SEARCH_INPUT_PORTS, WEB_SEARCH_OUTPUT_PORTS

from units.env_loaders import register_env_loader


def register_web_units() -> None:
    """Register browser and web_search for the web environment."""
    register_browser()
    register_web_search()


register_env_loader("web", register_web_units)

__all__ = [
    "register_web_units",
    "register_browser",
    "register_web_search",
    "BROWSER_INPUT_PORTS",
    "BROWSER_OUTPUT_PORTS",
    "WEB_SEARCH_INPUT_PORTS",
    "WEB_SEARCH_OUTPUT_PORTS",
]
