"""
NormalizeGraph unit: normalize a graph dict to ProcessGraph and output as dict (wraps core.normalizer.to_process_graph).

Input: graph (Any) — raw graph (dict or ProcessGraph).
Output: graph (Any) — normalized graph as dict; error (str) — message on failure.
Params: format (optional) — "dict" | "yaml"; default "dict".
Used by the GUI and runners so normalization is done via workflow instead of direct Core dependency.
"""
from __future__ import annotations

from typing import Any, Literal, cast

from units.registry import UnitSpec, register_unit

NORMALIZE_GRAPH_INPUT_PORTS = [("graph", "Any")]
NORMALIZE_GRAPH_OUTPUT_PORTS = [("graph", "Any"), ("error", "str")]


FormatProcess = Literal["yaml", "dict",]

def _normalize_graph_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    graph = inputs.get("graph")
    fmt_raw = params.get("format") or "dict"

    if isinstance(fmt_raw, str):
        fmt_str = fmt_raw.strip().lower() or "dict"
    else:
        fmt_str = "dict"

    allowed = {"yaml", "dict"}
    if fmt_str not in allowed:
        fmt_str = "dict"

    fmt = cast(FormatProcess, fmt_str)

    if graph is None:
        return ({"graph": None, "error": "NormalizeGraph: graph missing"}, state)

    try:
        from core.normalizer import to_process_graph

        pg = to_process_graph(graph, format=fmt)
        out = pg.model_dump(by_alias=True) if hasattr(pg, "model_dump") else pg
        return ({"graph": out, "error": None}, state)
    except Exception as e:
        return ({"graph": None, "error": str(e)[:200]}, state)


def register_normalize_graph() -> None:
    register_unit(UnitSpec(
        type_name="NormalizeGraph",
        input_ports=NORMALIZE_GRAPH_INPUT_PORTS,
        output_ports=NORMALIZE_GRAPH_OUTPUT_PORTS,
        step_fn=_normalize_graph_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Normalize graph dict to ProcessGraph and output as dict (wraps core.normalizer.to_process_graph). Params: format.",
    ))


__all__ = ["register_normalize_graph", "NORMALIZE_GRAPH_INPUT_PORTS", "NORMALIZE_GRAPH_OUTPUT_PORTS"]
