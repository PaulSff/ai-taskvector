"""
HTML-to-text unit: convert HTML input to plain text (Markdown-style).
Web environment (Python-only); not exported to Node-RED/PyFlow.

Input: HTML string (e.g. from browser unit). Output: plain text suitable for
LLMs/agents. Uses html2text when available; otherwise returns input as-is.
Optional dependency: pip install html2text
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

HTML_TO_TEXT_INPUT_PORTS = [("in", "Any")]
HTML_TO_TEXT_OUTPUT_PORTS = [("out", "Any"), ("error", "str")]


def _html_to_text_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = None
    if inputs:
        raw = next(iter(inputs.values()), None)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return ({"out": "", "error": None}, state)
    html = str(raw).strip()

    err: str | None = None
    try:
        import html2text
        h = html2text.HTML2Text()
        h.ignore_links = bool((params or {}).get("ignore_links", False))
        text = h.handle(html)
    except ImportError:
        err = "Missing package: pip install html2text; passing through raw HTML"
        text = html  # pass through if html2text not installed

    return ({"out": text, "error": err}, state)


def register_html_to_text() -> None:
    register_unit(UnitSpec(
        type_name="html_to_text",
        input_ports=HTML_TO_TEXT_INPUT_PORTS,
        output_ports=HTML_TO_TEXT_OUTPUT_PORTS,
        step_fn=_html_to_text_step,
        environment_tags=["web"],
        environment_tags_are_agnostic=False,
        runtime_scope=None,
        description="Convert HTML to plain text (Markdown-style). Input from browser or other; output for LLMs. Optional: pip install html2text.",
    ))


__all__ = [
    "register_html_to_text",
    "HTML_TO_TEXT_INPUT_PORTS",
    "HTML_TO_TEXT_OUTPUT_PORTS",
]
