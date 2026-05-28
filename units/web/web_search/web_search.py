"""
Web search unit: query DuckDuckGo (ddgs) and output results as text.
Web environment (Python-only); not exported to Node-RED/PyFlow.

Query comes from params.query or from the first input. Output is a text block:
one result per block (title, URL, snippet). Prefers ddgs (pip install ddgs),
falls back to duckduckgo_search for older installs.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from units.registry import UnitSpec, register_unit

WEB_SEARCH_INPUT_PORTS = [("in", "Any")]
WEB_SEARCH_OUTPUT_PORTS = [("out", "Any"), ("error", "str")]


def _normalize_query(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, (bytes, bytearray)):
        return raw.decode("utf-8", "replace").strip()
    if isinstance(raw, (list, tuple)):
        return " ".join(map(str, raw)).strip()
    return str(raw).strip()


def _collect_param(
    params: Optional[Dict[str, Any]], name: str, default: Any = None
) -> Any:
    return (params or {}).get(name, default)


def _format_result(r: Any) -> str:
    if isinstance(r, dict):
        title = r.get("title") or r.get("Title") or ""
        href = r.get("href") or r.get("link") or r.get("url") or ""
        body = r.get("body") or r.get("snippet") or r.get("Body") or ""
        return f"{title}\n  {href}\n  {body}"
    return str(r)


def _web_search_step(
    params: Dict[str, Any],
    inputs: Dict[str, Any],
    state: Dict[str, Any],
    dt: float,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Run a DuckDuckGo (ddgs/duckduckgo_search) text search.

    Params (via params dict):
      - query or q: query string (optional; falls back to first input)
      - max_results: int (default 10, clamped 1..100)
      - region: optional region string (default None -> library default)
      - safesearch: 'moderate'|'off'|'strict' (default 'moderate')
      - timelimit: optional time limit for results
      - page: int (default 1)
      - backend: ddgs backend arg (default 'auto')
    """
    raw_q = _collect_param(params, "query") or _collect_param(params, "q")
    if not raw_q and inputs:
        raw_q = next(iter(inputs.values()), None)
    query = _normalize_query(raw_q)
    if not query:
        return ({"out": "", "error": None}, state)

    try:
        max_results = int(_collect_param(params, "max_results", 10) or 10)
    except (TypeError, ValueError):
        max_results = 10
    max_results = max(1, min(max_results, 100))

    region = _collect_param(params, "region", None)
    safesearch = _collect_param(params, "safesearch", "moderate")
    timelimit = _collect_param(params, "timelimit", None)
    try:
        page = int(_collect_param(params, "page", 1) or 1)
    except (TypeError, ValueError):
        page = 1
    backend = _collect_param(params, "backend", "auto")

    err: Optional[str] = None
    try:
        try:
            from ddgs import DDGS  # type: ignore
        except Exception:
            from ddgs import DDGS  # type: ignore

        ddgs_client = DDGS()
        raw_results: Iterable[Any] = ddgs_client.text(
            query=query,
            region=region,
            safesearch=safesearch,
            timelimit=timelimit,
            max_results=max_results,
            page=page,
            backend=backend,
        )
        results: List[str] = [_format_result(r) for r in raw_results]

    except ImportError:
        err = "Missing package: pip install ddgs"
        return ({"out": f"(Install ddgs: {err})", "error": err}, state)
    except Exception as e:
        err = str(e)[:200]
        return ({"out": f"(Search error: {err})", "error": err}, state)

    out_text = "\n\n".join(results) if results else ""
    return ({"out": out_text, "error": None}, state)


def run_web_search(query: str, max_results: int = 10) -> str:
    out, _ = _web_search_step({"query": query, "max_results": max_results}, {}, {}, 0.0)
    value = out.get("out")
    return value if isinstance(value, str) else ""


def register_web_search() -> None:
    register_unit(
        UnitSpec(
            type_name="web_search",
            input_ports=WEB_SEARCH_INPUT_PORTS,
            output_ports=WEB_SEARCH_OUTPUT_PORTS,
            step_fn=_web_search_step,
            environment_tags=["web"],
            environment_tags_are_agnostic=False,
            runtime_scope=None,
            description=(
                "Web search (DuckDuckGo/ddgs): params.query or input; output is title/URL/snippet per result. "
                "Web env only. Prefers ddgs package."
            ),
        )
    )


__all__ = [
    "register_web_search",
    "run_web_search",
    "WEB_SEARCH_INPUT_PORTS",
    "WEB_SEARCH_OUTPUT_PORTS",
]
