"""
Minify-HTML unit: minify HTML to reduce size (whitespace, optional JS/CSS).
Web environment (Python-only); not exported to Node-RED/PyFlow.

Input: HTML string (e.g. from browser unit). Output: minified HTML.
Optional dependency: pip install minify-html
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

MINIFY_HTML_INPUT_PORTS = [("in", "Any")]
MINIFY_HTML_OUTPUT_PORTS = [("out", "Any")]


def _minify_html_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = None
    if inputs:
        raw = next(iter(inputs.values()), None)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return ({"out": ""}, state)
    html = str(raw).strip()
    par = params or {}

    try:
        import minify_html
    except ImportError:
        return (
            {"out": "(Install minify-html: pip install minify-html)"},
            state,
        )

    minify_js = bool(par.get("minify_js", False))
    minify_css = bool(par.get("minify_css", False))
    keep_comments = bool(par.get("keep_comments", False))
    keep_spaces_between_attributes = bool(par.get("keep_spaces_between_attributes", False))
    remove_processing_instructions = bool(par.get("remove_processing_instructions", True))

    out = minify_html.minify(
        html,
        minify_js=minify_js,
        minify_css=minify_css,
        keep_comments=keep_comments,
        keep_spaces_between_attributes=keep_spaces_between_attributes,
        remove_processing_instructions=remove_processing_instructions,
    )
    return ({"out": out}, state)


def register_minify_html() -> None:
    register_unit(UnitSpec(
        type_name="minify_html",
        input_ports=MINIFY_HTML_INPUT_PORTS,
        output_ports=MINIFY_HTML_OUTPUT_PORTS,
        step_fn=_minify_html_step,
        environment_tags=["web"],
        environment_tags_are_agnostic=False,
        runtime_scope=None,
        description="Minify HTML (whitespace, optional JS/CSS). Input from browser or other. Optional: pip install minify-html.",
    ))


__all__ = [
    "register_minify_html",
    "MINIFY_HTML_INPUT_PORTS",
    "MINIFY_HTML_OUTPUT_PORTS",
]
