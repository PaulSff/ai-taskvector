"""Browser unit: fetch URL, output raw response body."""
from units.web.browser.browser import (
    BROWSER_INPUT_PORTS,
    BROWSER_OUTPUT_PORTS,
    fetch_url,
    register_browser,
)

__all__ = ["register_browser", "fetch_url", "BROWSER_INPUT_PORTS", "BROWSER_OUTPUT_PORTS"]
