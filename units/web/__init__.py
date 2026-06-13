"""Web environment units: browser, web_search, html_to_text, beautifulsoup, minify_html. Python-only; not exported to Node-RED/PyFlow."""

from units.env_loaders import register_env_loader
from units.web.beautifulsoup import (
    BEAUTIFULSOUP_INPUT_PORTS,
    BEAUTIFULSOUP_OUTPUT_PORTS,
    html_to_text,
    register_beautifulsoup,
)
from units.web.browser import (
    BROWSER_INPUT_PORTS,
    BROWSER_OUTPUT_PORTS,
    fetch_url,
    register_browser,
)
from units.web.html_to_text import (
    HTML_TO_TEXT_INPUT_PORTS,
    HTML_TO_TEXT_OUTPUT_PORTS,
    register_html_to_text,
)
from units.web.minify_html import (
    MINIFY_HTML_INPUT_PORTS,
    MINIFY_HTML_OUTPUT_PORTS,
    register_minify_html,
)
from units.web.web_search import (
    WEB_SEARCH_INPUT_PORTS,
    WEB_SEARCH_OUTPUT_PORTS,
    register_web_search,
    run_web_search,
)


def register_web_units() -> None:
    """Register browser, web_search, html_to_text, beautifulsoup, and minify_html for the web environment."""
    register_browser()
    register_web_search()
    register_html_to_text()
    register_beautifulsoup()
    register_minify_html()


register_env_loader("web", register_web_units)

__all__ = [
    "register_web_units",
    "register_browser",
    "register_web_search",
    "register_html_to_text",
    "register_beautifulsoup",
    "register_minify_html",
    "fetch_url",
    "run_web_search",
    "html_to_text",
    "BROWSER_INPUT_PORTS",
    "BROWSER_OUTPUT_PORTS",
    "WEB_SEARCH_INPUT_PORTS",
    "WEB_SEARCH_OUTPUT_PORTS",
    "HTML_TO_TEXT_INPUT_PORTS",
    "HTML_TO_TEXT_OUTPUT_PORTS",
    "BEAUTIFULSOUP_INPUT_PORTS",
    "BEAUTIFULSOUP_OUTPUT_PORTS",
    "MINIFY_HTML_INPUT_PORTS",
    "MINIFY_HTML_OUTPUT_PORTS",
]
