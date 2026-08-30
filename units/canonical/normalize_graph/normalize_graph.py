"""
NormalizeGraph unit: normalize a graph dict to ProcessGraph and output as dict (wraps core.normalizer.to_process_graph).

Input: graph (Any) — raw graph (dict or ProcessGraph).
Output: graph (Any) — normalized graph as dict; error (str) — message on failure.
Params: format (optional) — "dict" | "yaml"; default "dict".
Used by the GUI and runners so normalization is done via workflow instead of direct Core dependency.
"""
from __future__ import annotations

from typing import cast

from core.schemas.primitives import (
    FormatProcess,
    RawProcessInput,
    is_json_document,
    is_json_object,
    is_model_dumpable,
)
from units.registry import UnitSpec, register_unit

NORMALIZE_GRAPH_INPUT_PORTS = [("graph", "RawProcessInput")]
NORMALIZE_GRAPH_OUTPUT_PORTS = [("graph", "ProcessGraph"), ("error", "str")]


def _validated_raw_process_input(
    value: object,
) -> RawProcessInput | None:
    if isinstance(value, str):
        return value

    if is_json_document(value):
        return value

    if is_model_dumpable(value):
        try:
            dumped = value.model_dump(by_alias=True)
        except (TypeError, ValueError, RuntimeError):
            return None

        if is_json_object(dumped):
            return dumped

    return None


def _normalize_graph_step(
    params: dict[str, object],
    inputs: dict[str, object],
    state: dict[str, object],
    dt: float,
) -> tuple[dict[str, object], dict[str, object]]:
    graph = inputs.get("graph")
    fmt_raw = params.get("format") or "dict"

    if isinstance(fmt_raw, str):
        fmt_str = fmt_raw.strip().lower() or "dict"
    else:
        fmt_str = "dict"

    if fmt_str not in {"yaml", "dict"}:
        fmt_str = "dict"

    fmt = cast(FormatProcess, fmt_str)

    if graph is None:
        return (
            {"graph": None, "error": "NormalizeGraph: graph missing"},
            state,
        )

    raw_graph = _validated_raw_process_input(graph)
    if raw_graph is None:
        return (
            {
                "graph": None,
                "error": (
                    "NormalizeGraph: graph must be a JSON object, "
                    "JSON array, string, or ProcessGraph"
                ),
            },
            state,
        )

    try:
        from core.normalizer import to_process_graph

        pg = to_process_graph(raw_graph, format=fmt)
        out = (
            pg.model_dump(by_alias=True)
            if hasattr(pg, "model_dump")
            else pg
        )

        return ({"graph": out, "error": None}, state)

    except ImportError as e:
        return (
            {"graph": None, "error": str(e)[:200]},
            state,
        )

    except (TypeError, ValueError, RuntimeError) as e:
        return (
            {"graph": None, "error": str(e)[:200]},
            state,
        )


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


__all__ = ["NORMALIZE_GRAPH_INPUT_PORTS", "NORMALIZE_GRAPH_OUTPUT_PORTS", "register_normalize_graph"]
