"""
Web search unit: query DuckDuckGo (or similar) and output results as text.
Web environment (Python-only); not exported to Node-RED/PyFlow.

Query comes from params.query or from the first input. Output is a text block:
one line per result (title, URL, snippet). Requires the duckduckgo-search package
(optional): pip install duckduckgo-search
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

WEB_SEARCH_INPUT_PORTS = [("in", "Any")]  # optional: query from upstream
WEB_SEARCH_OUTPUT_PORTS = [("out", "Any"), ("error", "str")]


def _web_search_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    query = (params or {}).get("query") or (params or {}).get("q")
    if not query and inputs:
        query = next(iter(inputs.values()), None)
    if not query:
        return ({"out": "", "error": None}, state)
    query = str(query).strip()
    max_results = int((params or {}).get("max_results") or 10)
    max_results = max(1, min(max_results, 20))

    err: str | None = None
    try:
        from duckduckgo_search import DDGS
        results = list(DDGS().text(query, max_results=max_results))
    except ImportError:
        try:
            from ddgs import DDGS
            results = list(DDGS().text(query, max_results=max_results))
        except ImportError:
            err = "Missing package: pip install duckduckgo-search"
            return (
                {"out": f"(Install duckduckgo-search or ddgs: {err})", "error": err},
                state,
            )
    except Exception as e:
        err = str(e)[:200]
        return ({"out": f"(Search error: {e})", "error": err}, state)

    lines: list[str] = []
    for r in results:
        if isinstance(r, dict):
            title = r.get("title") or r.get("Title") or ""
            href = r.get("href") or r.get("link") or r.get("url") or ""
            body = r.get("body") or r.get("snippet") or r.get("Body") or ""
            lines.append(f"{title}\n  {href}\n  {body}")
        else:
            lines.append(str(r))
    return ({"out": "\n\n".join(lines) if lines else "", "error": None}, state)


def run_web_search(query: str, max_results: int = 10) -> str:
    """
    Run the web_search unit: query DuckDuckGo and return plain text (title, URL, snippet per result).
    Not HTML; suitable for LLM context or follow-up turns.
    """
    out, _ = _web_search_step(
        {"query": query, "max_results": max_results},
        {},
        {},
        0.0,
    )
    return (out.get("out") or "") if isinstance(out.get("out"), str) else ""


def register_web_search() -> None:
    register_unit(UnitSpec(
        type_name="web_search",
        input_ports=WEB_SEARCH_INPUT_PORTS,
        output_ports=WEB_SEARCH_OUTPUT_PORTS,
        step_fn=_web_search_step,
        environment_tags=["web"],
        environment_tags_are_agnostic=False,
        runtime_scope=None,
        description="Web search (DuckDuckGo): params.query or input; output is title/URL/snippet per result. Web env only. Requires duckduckgo-search.",
    ))


__all__ = ["register_web_search", "run_web_search", "WEB_SEARCH_INPUT_PORTS", "WEB_SEARCH_OUTPUT_PORTS"]
