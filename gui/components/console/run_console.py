"""
Helpers for the workflow run console: format executor output, align Debug log paths with settings.

Used by :mod:`gui.components.console.console` for the bottom panel; ``format_run_outputs`` /
``debug_log_param_overrides_for_graph_dict`` have no Flet dependency.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Literal, Optional

from core.schemas.process_graph import ProcessGraph

JOB_PUB_ENDPOINT = "tcp://127.0.0.1:6660"
RESULT_SUB_ENDPOINT = "tcp://127.0.0.1:6670"
RESPONSE_PUB_ENDPOINT = RESULT_SUB_ENDPOINT

FormatProcess = Literal["dict", "yaml", "pyflow"]


def debug_log_param_overrides_for_graph_dict(
    graph_dict: Any, log_path: str
) -> dict[str, dict[str, Any]]:
    """Build ``unit_param_overrides`` for RunWorkflow so every **Debug** unit writes to ``log_path``.

    Without this, Debug falls back to ``workflow.log`` while the console grep uses
    ``get_debug_log_path()`` from settings — paths diverge after the user changes the setting.
    """
    if not isinstance(graph_dict, dict):
        return {}
    units = graph_dict.get("units")
    if not isinstance(units, list):
        return {}
    lp = (log_path or "").strip()
    if not lp:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for u in units:
        if not isinstance(u, dict):
            continue
        if str(u.get("type") or "").strip() != "Debug":
            continue
        uid = u.get("id")
        if isinstance(uid, str) and uid.strip():
            out[uid.strip()] = {"log_path": lp}
    return out


def format_run_outputs(outputs: dict[str, Any]) -> str:
    """Format executor outputs as terminal log lines."""
    lines: list[str] = []
    for unit_id, port_values in sorted(outputs.items()):
        if not isinstance(port_values, dict):
            lines.append(f"[{unit_id}] (non-dict output)")
            continue
        for port_name, value in sorted(port_values.items()):
            if value is None:
                s = "None"
            elif isinstance(value, str):
                s = value[:500] + ("..." if len(value) > 500 else "")
            elif isinstance(value, (dict, list)):
                try:
                    s = json.dumps(value, ensure_ascii=False)[:500]
                    if len(json.dumps(value)) > 500:
                        s += "..."
                except (TypeError, ValueError):
                    s = repr(value)[:500]
            else:
                s = str(value)[:500]
            lines.append(f"  {unit_id}.{port_name}: {s}")
    return "\n".join(lines) if lines else "(no outputs)"


def build_initial_inputs_for_run(
    graph: ProcessGraph, user_message: str
) -> dict[str, dict[str, Any]]:
    """Build initial_inputs for Inject units: each gets {'data': user_message} when non-empty.
    When empty, omit so Injects use params or Template connection."""
    initial: dict[str, dict[str, Any]] = {}
    msg = (user_message or "").strip()
    if not msg:
        return initial
    for u in graph.units:
        if u.type == "Inject":
            initial[u.id] = {"data": msg}
    return initial


# --- publish graph job and await result (API: inputs, outputs only) ---


async def run_graph(
    graph: ProcessGraph,
    initial_inputs: dict[str, dict[str, Any]] | None = None,
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    format: FormatProcess = "dict",
    execution_timeout_s: float | None = None,
) -> dict[str, Any]:
    """
    Publish the workflow graph to the server and await the result.

    Returns outputs only (API: inputs, outputs).
    """
    from gui.chat.utils import collect_workflow_errors
    from runtime import ZmqPublisher, ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics
    from runtime.run import WorkflowTimeoutError

    initial_inputs = initial_inputs or {}
    run_id = uuid.uuid4().hex

    job_pub = ZmqPublisher(pub_endpoint=JOB_PUB_ENDPOINT, topics=ZmqTopics())

    topics = ZmqTopics()
    sub = ZmqSubscriber(
        config=ZmqSubscriptionConfig(
            sub_endpoint=RESULT_SUB_ENDPOINT,
            topics=(topics.token, topics.result, topics.error),
            accept_topics=None,
            rcvtimeo_ms=200,
        )
    )

    has_workflow_error = False
    workflow_error = ""
    final_outputs: Optional[dict[str, Any]] = None

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
        graph_dict = graph.model_dump()

        job_pub.publish_job(
            run_id=run_id,
            workflow_graph=graph_dict,  # type: ignore[arg-type]
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format=format,
            response_endpoint=RESPONSE_PUB_ENDPOINT,
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

    outputs = final_outputs or {}
    _ = collect_workflow_errors(outputs)  # preserve previous behavior side effects
    return outputs
