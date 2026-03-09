"""
Browser unit: fetch a URL and output the page content as text.
Web environment (Python-only); not exported to Node-RED/PyFlow.

URL comes from params.url or from the first input. Uses HTTP GET; returns the
response body (raw text). No JavaScript execution; for full browser behavior use
an external tool (e.g. Playwright) via exec or function. requests is used if
available; otherwise urllib.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

BROWSER_INPUT_PORTS = [("in", "Any")]  # optional: URL from upstream
BROWSER_OUTPUT_PORTS = [("out", "Any")]

_MAX_BODY = 1024 * 1024  # 1 MB cap


def _browser_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    url = (params or {}).get("url")
    if not url and inputs:
        url = next(iter(inputs.values()), None)
    if not url:
        return ({"out": ""}, state)
    url = str(url).strip()
    timeout = float((params or {}).get("timeout") or 15)
    timeout = max(1, min(timeout, 60))

    try:
        try:
            import requests
            r = requests.get(url, timeout=timeout, stream=True)
            r.raise_for_status()
            content = b""
            for chunk in r.iter_content(chunk_size=8192):
                content += chunk
                if len(content) > _MAX_BODY:
                    content = content[:_MAX_BODY] + b"\n... (truncated)"
                    break
            text = content.decode("utf-8", errors="replace")
        except ImportError:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; DAG-browser/1.0)"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read(_MAX_BODY + 1)
                if len(content) > _MAX_BODY:
                    content = content[:_MAX_BODY] + b"\n... (truncated)"
                text = content.decode("utf-8", errors="replace")
    except Exception as e:
        return ({"out": f"(Fetch error: {e})"}, state)

    return ({"out": text}, state)


def register_browser() -> None:
    register_unit(UnitSpec(
        type_name="browser",
        input_ports=BROWSER_INPUT_PORTS,
        output_ports=BROWSER_OUTPUT_PORTS,
        step_fn=_browser_step,
        environment_tags=["web"],
        environment_tags_are_agnostic=False,
        runtime_scope=None,
        description="Fetch URL: params.url or input; output is page body text (GET, no JS). Web env only.",
    ))


__all__ = ["register_browser", "BROWSER_INPUT_PORTS", "BROWSER_OUTPUT_PORTS"]
