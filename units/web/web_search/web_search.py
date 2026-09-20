"""
Web search unit: query DuckDuckGo (ddgs) and output results as text.

Query comes from params.query or from the first input.

Output:
  - out: one result per block containing title, URL, and snippet
  - error: an error message, or None on success

Prefers the modern `ddgs` package and falls back to
`duckduckgo_search` for older installations.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ddgs.exceptions import DDGSException

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
    params: dict[str, Any] | None,
    name: str,
    default: Any = None,
) -> Any:
    return (params or {}).get(name, default)


def _format_result(result: Any) -> str:
    if isinstance(result, dict):
        title = (
            result.get("title")
            or result.get("Title")
            or ""
        )

        href = (
            result.get("href")
            or result.get("link")
            or result.get("url")
            or ""
        )

        body = (
            result.get("body")
            or result.get("snippet")
            or result.get("Body")
            or ""
        )

        return f"{title}\n  {href}\n  {body}"

    return str(result)


def _get_query(
    params: dict[str, Any],
    inputs: dict[str, Any],
) -> str:
    raw_query = _collect_param(params, "query")

    if not _normalize_query(raw_query):
        raw_query = _collect_param(params, "q")

    if not _normalize_query(raw_query) and inputs:
        raw_query = next(iter(inputs.values()), None)

    return _normalize_query(raw_query)


def _web_search_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Run a DuckDuckGo text search.

    Parameters:
      query: Search query. Falls back to q, then the first input.
      q: Alias for query.
      max_results: Number of results, clamped to 1..100.
      region: Optional region string.
      safesearch: moderate, off, or strict.
      timelimit: Optional time limit such as d, w, m, or y.
      page: Result page number.
      backend: Optional ddgs backend.
    """

    query = _get_query(params, inputs)

    if not query:
        return (
            {
                "out": "",
                "error": "Search query is empty",
            },
            state,
        )

    try:
        max_results = int(
            _collect_param(params, "max_results", 10) or 10
        )
    except (TypeError, ValueError):
        max_results = 10

    max_results = max(1, min(max_results, 100))

    try:
        page = int(_collect_param(params, "page", 1) or 1)
    except (TypeError, ValueError):
        page = 1

    page = max(1, page)

    region = _collect_param(params, "region")
    safesearch = _collect_param(params, "safesearch", "moderate")
    timelimit = _collect_param(params, "timelimit")
    backend = _collect_param(params, "backend")

    try:
        try:
            from ddgs import DDGS  # type: ignore

            package_name = "ddgs"

        except ImportError:
            from duckduckgo_search import DDGS  # type: ignore

            package_name = "duckduckgo_search"

        # Do not pass None values to the library. Some versions of ddgs
        # call string methods such as .split() on optional arguments.
        search_kwargs: dict[str, Any] = {
            "max_results": max_results,
        }

        if region:
            search_kwargs["region"] = str(region)

        if safesearch:
            search_kwargs["safesearch"] = str(safesearch)

        if timelimit:
            search_kwargs["timelimit"] = str(timelimit)

        # These options are supported by current ddgs versions. Avoid
        # passing them to older duckduckgo_search installations.
        if package_name == "ddgs":
            if page:
                search_kwargs["page"] = page

            if backend:
                search_kwargs["backend"] = str(backend)

        ddgs_client = DDGS()

        # Pass the query positionally for compatibility across versions.
        raw_results: Iterable[Any] = ddgs_client.text(
            query,
            **search_kwargs,
        )

        results = [
            _format_result(result)
            for result in raw_results
        ]

        output_text = "\n\n".join(results)

        return (
            {
                "out": output_text,
                "error": None,
            },
            state,
        )

    except ImportError:
        error = (
            "Missing search package. Install one of: "
            "`python -m pip install ddgs` or "
            "`python -m pip install duckduckgo_search`"
        )

        return (
            {
                "out": f"(Search error: {error})",
                "error": error,
            },
            state,
        )

    except DDGSException as exc:
        # Catches DDGSException and backend/network errors so they are
        # returned through the error output instead of crashing the loop.
        error = f"{type(exc).__name__}: {exc}".strip()
        error = error[:500]

        return (
            {
                "out": f"(Search error: {error})",
                "error": error,
            },
            state,
        )


def run_web_search(
    query: str,
    max_results: int = 10,
) -> str:
    outputs, _ = _web_search_step(
        {
            "query": query,
            "max_results": max_results,
        },
        {},
        {},
        0.0,
    )

    value = outputs.get("out")
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
                "Web search using ddgs or duckduckgo_search. "
                "The query comes from params.query, params.q, "
                "or the first input. Results contain title, URL, "
                "and snippet."
            ),
        )
    )


__all__ = [
    "WEB_SEARCH_INPUT_PORTS",
    "WEB_SEARCH_OUTPUT_PORTS",
    "register_web_search",
    "run_web_search",
]
