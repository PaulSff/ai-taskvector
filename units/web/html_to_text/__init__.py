"""HTML-to-text unit: HTML → plain text (Markdown-style)."""
from units.web.html_to_text.html_to_text import (
    HTML_TO_TEXT_INPUT_PORTS,
    HTML_TO_TEXT_OUTPUT_PORTS,
    register_html_to_text,
)

__all__ = [
    "register_html_to_text",
    "HTML_TO_TEXT_INPUT_PORTS",
    "HTML_TO_TEXT_OUTPUT_PORTS",
]
