"""
BeautifulSoup4 unit: parse HTML and extract text, links, tables, or markup.
Web environment (Python-only); not exported to Node-RED/PyFlow.

Input: HTML string (e.g. from browser unit). Output: extracted content as string.
Params: mode ("text" | "links" | "tables" | "markup"), optional selector (CSS selector),
  optional limit (max links or tables). Optional dependency: pip install beautifulsoup4
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

BEAUTIFULSOUP_INPUT_PORTS = [("in", "Any")]
BEAUTIFULSOUP_OUTPUT_PORTS = [("out", "Any")]


def _beautifulsoup_step(
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
    mode = (par.get("mode") or "text").strip().lower()
    selector = par.get("selector") or par.get("css_selector")
    limit = int(par.get("limit") or 0)  # 0 = no limit

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return (
            {"out": "(Install beautifulsoup4: pip install beautifulsoup4)"},
            state,
        )

    soup = BeautifulSoup(html, "html.parser")
    if selector:
        try:
            root = soup.select_one(selector) or soup
        except Exception:
            root = soup
    else:
        root = soup

    if mode == "text":
        out = root.get_text(separator="\n", strip=True)
    elif mode == "links":
        links = []
        for a in root.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            if not href or href.startswith("#"):
                continue
            text = (a.get_text() or "").strip()
            links.append(f"{href}\t{text}" if text else href)
            if limit and len(links) >= limit:
                break
        out = "\n".join(links)
    elif mode == "tables":
        rows_out = []
        for table in root.find_all("table")[: limit or None]:
            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
                if cells:
                    rows_out.append("\t".join(cells))
            rows_out.append("")  # separator between tables
        out = "\n".join(rows_out).strip()
    elif mode == "markup":
        out = root.prettify()
    else:
        out = root.get_text(separator="\n", strip=True)

    return ({"out": out}, state)


def register_beautifulsoup() -> None:
    register_unit(UnitSpec(
        type_name="beautifulsoup",
        input_ports=BEAUTIFULSOUP_INPUT_PORTS,
        output_ports=BEAUTIFULSOUP_OUTPUT_PORTS,
        step_fn=_beautifulsoup_step,
        environment_tags=["web"],
        environment_tags_are_agnostic=False,
        runtime_scope=None,
        description="Parse HTML with BeautifulSoup4: mode=text|links|tables|markup, optional selector/limit. Optional: pip install beautifulsoup4.",
    ))


__all__ = [
    "register_beautifulsoup",
    "BEAUTIFULSOUP_INPUT_PORTS",
    "BEAUTIFULSOUP_OUTPUT_PORTS",
]
