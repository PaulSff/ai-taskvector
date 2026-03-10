"""Minify-HTML unit: reduce HTML size (whitespace, optional JS/CSS)."""
from units.web.minify_html.minify_html import (
    MINIFY_HTML_INPUT_PORTS,
    MINIFY_HTML_OUTPUT_PORTS,
    register_minify_html,
)

__all__ = [
    "register_minify_html",
    "MINIFY_HTML_INPUT_PORTS",
    "MINIFY_HTML_OUTPUT_PORTS",
]
