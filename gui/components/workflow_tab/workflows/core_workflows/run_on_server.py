"""
Publish workflows to the workflow server and await results (GUI never runs workflows directly).

JSON files in this package (under ``workflows/core_workflows/``) and sibling
``workflows/agents_workflows/`` are required.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from runtime import (
    ZmqPublisher,
    ZmqSubscriber,
    ZmqSubscriptionConfig,
    ZmqTopics,
)
from runtime.run import WorkflowTimeoutError

_CORE_WORKFLOWS_DIR = Path(__file__).resolve().parent
_agents_WORKFLOWS_DIR = _CORE_WORKFLOWS_DIR.parent / "agents_workflows"

_UNITS_LIBRARY_PATHS_SINGLE = _agents_WORKFLOWS_DIR / "units_library_paths_single.json"

# ---- fixed endpoint pools (configure N >= max concurrent calls) ----
N = 10

JOB_PUB_ENDPOINTS = [f"tcp://127.0.0.1:{6621 + 2 * i}" for i in range(N)]
RESPONSE_ENDPOINTS = [f"tcp://127.0.0.1:{6631 + 2 * i}" for i in range(N)]
RESPONSE_SUB_ENDPOINTS = RESPONSE_ENDPOINTS


def _missing_workflow_msg(path: Path) -> str:
    return f"Required workflow file not found: {path}"


FormatProcess = str  # Literal["dict","yaml","pyflow"] if you want


# ---- internal slot allocator (no slot in public APIs) ----
_slot_sem = asyncio.Semaphore(N)
_slot_next = 0
_slot_lock = asyncio.Lock()


async def _acquire_slot() -> int:
    global _slot_next
    await _slot_sem.acquire()
    async with _slot_lock:
        slot = _slot_next
        _slot_next = (_slot_next + 1) % N
    return slot


async def _release_slot() -> None:
    _slot_sem.release()


# ---- refactored _publish_and_wait signature: no slot param ----
async def _publish_and_wait(
    path: Path,
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    *,
    format: FormatProcess = "dict",
    execution_timeout_s: float | None = None,
) -> dict[str, Any]:
    slot = await _acquire_slot()
    try:
        run_id = uuid.uuid4().hex
        wp = path.resolve()

        job_pub = ZmqPublisher(
            pub_endpoint=JOB_PUB_ENDPOINTS[slot],
            topics=ZmqTopics(),
        )

        resp_endpoint = RESPONSE_ENDPOINTS[slot]

        topics = ZmqTopics()
        sub = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=RESPONSE_SUB_ENDPOINTS[slot],
                topics=(topics.token, topics.result, topics.error),
                accept_topics=None,
                rcvtimeo_ms=200,
            )
        )

        final_outputs: Optional[dict[str, Any]] = None
        has_workflow_error = False
        workflow_error = ""

        async def _on_error(_topic: str, payload: dict[str, Any]) -> None:
            nonlocal has_workflow_error, workflow_error
            if payload.get("run_id") != run_id:
                return
            err = payload.get("error")
            workflow_error = err if isinstance(err, str) else str(err)
            has_workflow_error = True

        async def _on_result(_topic: str, payload: dict[str, Any]) -> None:
            nonlocal final_outputs
            if payload.get("run_id") != run_id:
                return
            outs = payload.get("outputs")
            final_outputs = outs if isinstance(outs, dict) else {}

        async def _on_token(_topic: str, _payload: dict[str, Any]) -> None:
            return

        sub.on(topics.token, _on_token)
        sub.on(topics.result, _on_result)
        sub.on(topics.error, _on_error)

        await asyncio.wait_for(sub.start(), timeout=30)

        try:
            job_pub.publish_job(
                run_id=run_id,
                workflow_path=str(wp),
                initial_inputs=initial_inputs,
                unit_param_overrides=unit_param_overrides or {},
                format=format,
                response_endpoint=resp_endpoint,
            )

            start = time.monotonic()
            while final_outputs is None and not has_workflow_error:
                if (
                    execution_timeout_s is not None
                    and (time.monotonic() - start) > execution_timeout_s
                ):
                    raise WorkflowTimeoutError(execution_timeout_s)
                await asyncio.sleep(0.01)

        finally:
            await sub.stop()

        if has_workflow_error:
            raise RuntimeError(workflow_error)

        return final_outputs or {}
    finally:
        await _release_slot()


async def run_graph_summary(graph: Any) -> dict[str, Any]:
    """Run GraphSummary workflow; return summary dict. No Core import in caller."""
    if graph is None:
        return {"units": [], "connections": []}

    g = (
        graph.model_dump(by_alias=True)
        if hasattr(graph, "model_dump")
        else (graph if isinstance(graph, dict) else {})
    )
    path = _CORE_WORKFLOWS_DIR / "graph_summary_single.json"
    if not path.is_file():
        return {"units": [], "connections": []}

    out = await _publish_and_wait(path, {"inject_graph": {"data": g}}, format="dict")
    summary = (out.get("graph_summary") or {}).get("summary")
    return summary if isinstance(summary, dict) else {"units": [], "connections": []}


async def run_units_library_source_paths(
    graph_summary: dict[str, Any] | None,
    implementation_links_for_types: list[str] | None,
) -> list[str]:
    """
    Run units_library_paths_single.json: UnitsLibrary → source_paths (registry already filled by server run).
    Used by Workflow Designer follow-ups instead of importing units.* in the GUI layer.
    """
    gs = graph_summary if isinstance(graph_summary, dict) else {}
    link = [
        str(x).strip() for x in (implementation_links_for_types or []) if str(x).strip()
    ]

    if not link or not _UNITS_LIBRARY_PATHS_SINGLE.is_file():
        return []

    out = await _publish_and_wait(
        _UNITS_LIBRARY_PATHS_SINGLE,
        {"inject_graph_summary": {"data": gs}},
        unit_param_overrides={
            "units_library": {"implementation_links_for_types": link}
        },
        format="dict",
    )

    raw = (out.get("units_library") or {}).get("source_paths")
    if not isinstance(raw, list):
        return []
    return [str(p) for p in raw if p is not None and str(p).strip()]


async def run_graph_diff(prev_graph: Any, current_graph: Any) -> str | None:
    """Run GraphDiff workflow; return diff string or None. No Core import in caller."""
    if prev_graph is None or current_graph is None:
        return None

    prev = (
        prev_graph.model_dump(by_alias=True)
        if hasattr(prev_graph, "model_dump")
        else (prev_graph if isinstance(prev_graph, dict) else {})
    )
    curr = (
        current_graph.model_dump(by_alias=True)
        if hasattr(current_graph, "model_dump")
        else (current_graph if isinstance(current_graph, dict) else {})
    )

    path = _CORE_WORKFLOWS_DIR / "graph_diff_single.json"
    if not path.is_file():
        return None

    out = await _publish_and_wait(
        path,
        {"inject_prev": {"data": prev}, "inject_curr": {"data": curr}},
        format="dict",
    )
    diff = (out.get("graph_diff") or {}).get("diff")
    return str(diff).strip() or None if diff else None


async def run_load_workflow(
    path_str: str, format: str | None = None
) -> tuple[dict[str, Any] | None, str | None]:
    """Run LoadWorkflow; return (graph_dict, error). No Core import in caller."""
    path = _CORE_WORKFLOWS_DIR / "load_workflow_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))

    overrides = {"load_workflow": {"format": format}} if format else {}
    out = await _publish_and_wait(
        path,
        {"inject_path": {"data": path_str}},
        unit_param_overrides=overrides,
        format="dict",
    )

    unit_out = out.get("load_workflow") or {}
    return (unit_out.get("graph"), unit_out.get("error"))


async def run_export_workflow(graph: Any, format: str) -> tuple[Any, str | None]:
    """Run ExportWorkflow; return (exported dict/list, error). No Core import in caller."""
    g = (
        graph.model_dump(by_alias=True)
        if hasattr(graph, "model_dump")
        else (graph if isinstance(graph, dict) else None)
    )
    if g is None:
        return (None, "ExportWorkflow: graph missing")

    path = _CORE_WORKFLOWS_DIR / "export_workflow_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))

    out = await _publish_and_wait(
        path,
        {"inject_graph": {"data": g}},
        unit_param_overrides={"export_workflow": {"format": format}},
        format="dict",
    )

    unit_out = out.get("export_workflow") or {}
    return (unit_out.get("exported"), unit_out.get("error"))


async def run_runtime_label(graph: Any) -> tuple[str, bool]:
    """Run RuntimeLabel workflow; return (label, is_native). No Core import in caller."""
    if graph is None:
        return ("canonical", True)

    g = (
        graph.model_dump(by_alias=True)
        if hasattr(graph, "model_dump")
        else (graph if isinstance(graph, dict) else {})
    )

    path = _CORE_WORKFLOWS_DIR / "runtime_label_single.json"
    if not path.is_file():
        return ("canonical", True)

    out = await _publish_and_wait(path, {"inject_graph": {"data": g}}, format="dict")
    unit_out = out.get("runtime_label") or {}
    return (
        str(unit_out.get("label", "canonical")),
        bool(unit_out.get("is_native", True)),
    )


async def run_apply_edits(
    graph: Any,
    edits: list[dict[str, Any]],
    graph_origin: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Run ApplyEdits workflow; return (graph_dict, error). No Core import in caller."""
    g = (
        graph.model_dump(by_alias=True)
        if hasattr(graph, "model_dump")
        else (graph if isinstance(graph, dict) else {})
    )

    path = _CORE_WORKFLOWS_DIR / "apply_edits_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))

    init = {
        "inject_graph": {"data": g},
        "inject_edits": {"data": edits},
        "inject_origin": {"data": graph_origin or ""},
    }
    out = await _publish_and_wait(path, init, format="dict")

    unit_out = out.get("apply_edits") or {}
    err = unit_out.get("error")
    if err:
        return (None, str(err)[:200])
    return (unit_out.get("graph"), None)


async def run_apply_training_config_edits(
    training_config: Any,
    edits: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    """Run ApplyTrainingConfigEdits workflow; return (config_dict, error)."""
    cfg = (
        training_config.model_dump(by_alias=True)
        if hasattr(training_config, "model_dump")
        else (training_config if isinstance(training_config, dict) else {})
    )

    path = _CORE_WORKFLOWS_DIR / "apply_training_config_edits_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))

    init = {
        "inject_training_config": {"data": cfg},
        "inject_edits": {"data": edits},
    }
    out = await _publish_and_wait(path, init, format="dict")

    unit_out = out.get("apply_training_config_edits") or {}
    err = unit_out.get("error")
    if err:
        return (None, str(err)[:500])

    merged = unit_out.get("config")
    return (merged if isinstance(merged, dict) else None, None)


async def run_normalize_graph(
    graph: Any, format: str = "dict"
) -> tuple[dict[str, Any] | None, str | None]:
    """Run NormalizeGraph workflow; return (graph_dict, error). No Core import in caller."""
    if graph is None:
        return (None, "NormalizeGraph: graph missing")

    g = (
        graph.model_dump(by_alias=True)
        if hasattr(graph, "model_dump")
        else (graph if isinstance(graph, dict) else {})
    )

    path = _CORE_WORKFLOWS_DIR / "normalize_graph_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))

    out = await _publish_and_wait(
        path,
        {"inject_graph": {"data": g}},
        unit_param_overrides={"normalize_graph": {"format": format}},
        format="dict",
    )
    unit_out = out.get("normalize_graph") or {}
    return (unit_out.get("graph"), unit_out.get("error"))


async def validate_graph_to_apply_for_canvas(graph: Any) -> tuple[Any, str | None]:
    if graph is None:
        return (None, "ValidateGraphToApply: graph missing")

    g = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else graph
    if not isinstance(g, dict):
        return (None, "ValidateGraphToApply: expected dict or model with model_dump")

    path = _CORE_WORKFLOWS_DIR / "validate_graph_to_apply_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))

    out = await _publish_and_wait(path, {"inject_graph": {"data": g}}, format="dict")
    unit_out = out.get("validate_graph_to_apply") or {}

    err = unit_out.get("error")
    if err:
        print("validate_graph_to_apply_for_canvas workflow error:", err)
        return (None, str(err))

    gd = unit_out.get("graph")
    if not isinstance(gd, dict):
        return (None, "ValidateGraphToApply: no graph in workflow output")

    return (gd, None)


async def run_clean_text_for_chat(text: str) -> str:
    """
    Run Inject → CleanText (units/semantics/clean_text) to remove fenced markdown/code and
    JSON-like noise from message text for history and previous-turn prompts.
    """
    from units.semantics import register_semantics_units

    register_semantics_units()

    path = _agents_WORKFLOWS_DIR / "clean_text_chat_single.json"
    raw = text if isinstance(text, str) else str(text or "")
    if not path.is_file():
        return raw.strip()

    out = await _publish_and_wait(path, {"inject_text": {"data": raw}}, format="dict")
    unit_out = out.get("clean_text") or {}
    return str(unit_out.get("text", "") or "")
