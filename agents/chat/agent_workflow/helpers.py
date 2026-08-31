"""Initial inputs, overrides, runtime label, and apply-result refresh for agent chat workflows."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from core.graph.summary import graph_summary
from gui.components.workflow_tab.process_graph import ProcessGraph
from units.registry import Data


def missing_workflow_msg(path: Path) -> str:
    return f"Required workflow file not found: {path}"


async def get_runtime_for_prompts(
    graph: ProcessGraph | None,
) -> Literal["native", "external"]:
    from services.workflows.core_workflows import run_runtime_label

    def _log(msg: str) -> None:
        print(
            f"[get_runtime_for_prompts] {msg} ts={time.time():.3f}",
            flush=True,
        )

    _log(
        f"enter graph_type={type(graph).__name__} "
        + f"graph_is_none={graph is None}"
    )

    if graph is None:
        _log("graph_none -> external")
        return "external"

    r = graph.runtime
    _log(f"read_runtime_field r={r!r}")

    if r in ("native", "external"):
        _log(f"runtime_field_valid -> {r}")
        return r

    _log("runtime_field_invalid_or_missing -> run_runtime_label(graph)")
    t0 = time.time()

    _, is_native = await run_runtime_label(graph)

    _log(
        f"run_runtime_label_done dt={(time.time() - t0):.3f}s "
        + f"is_native={is_native}"
    )

    out: Literal["native", "external"] = (
        "native" if is_native else "external"
    )
    _log(f"return {out}")
    return out


async def refresh_last_apply_result_after_canvas_apply(
    prev: Data | None,
    graph: ProcessGraph,
    *,
    supplement_summary: str = "",
) -> Data:
    previous = prev or {}

    base = str(previous.get("edits_summary") or "").strip()
    supplement = supplement_summary.strip()

    edits_summary = (
        f"{base}; {supplement}"
        if base and supplement
        else base or supplement or "applied"
    )

    graph_after = graph_summary(graph)

    return {
        "attempted": True,
        "success": True,
        "error": None,
        "edits_summary": edits_summary,
        "graph_after": graph_after,
    }


async def validate_graph_to_apply_for_canvas_async(
    graph: ProcessGraph | None,
) -> tuple[ProcessGraph | None, str | None]:
    if graph is None:
        return None, "ValidateGraphToApply: graph missing"

    try:
        validated_graph = ProcessGraph.model_validate(
            graph.model_dump(by_alias=True)
        )
    except ValidationError as exc:
        return None, f"ValidateGraphToApply: invalid graph: {exc}"

    return validated_graph, None
