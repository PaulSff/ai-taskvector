"""
Helpers for the workflow run console: format executor output, align Debug log paths with settings.

Used by :mod:`gui.components.console.console` for the bottom panel; ``format_run_outputs`` /
``debug_log_param_overrides_for_graph_dict`` have no Flet dependency.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Mapping
from typing import Literal, TypeGuard, cast

from core.schemas.process_graph import ProcessGraph
from gui.components.settings import (
    DEFAULT_CONSOLE_JOB_PUB_ENDPOINT,
    DEFAULT_CONSOLE_RESULT_SUB_ENDPOINT,
    DEFAULT_CONSOLE_WORKFLOWS_CONCURRENT_CALLS,
)
from runtime.run import WorkflowTimeoutError
from services.logging import setup_colored_logging
from services.server import (
    RoundRobinSlotAllocator,
    _parse_host_port,
)
from services.zmq import ZmqPublisher, ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics

JOB_PUB_ENDPOINT = DEFAULT_CONSOLE_JOB_PUB_ENDPOINT
RESULT_SUB_ENDPOINT = DEFAULT_CONSOLE_RESULT_SUB_ENDPOINT
RESPONSE_PUB_ENDPOINT = RESULT_SUB_ENDPOINT  # response endpoint published to

N = DEFAULT_CONSOLE_WORKFLOWS_CONCURRENT_CALLS

workflow_host, workflow_port = _parse_host_port(JOB_PUB_ENDPOINT)
resp_host, resp_port = _parse_host_port(RESULT_SUB_ENDPOINT)

# Fixed endpoint pools (configure N >= max concurrent calls)
JOB_PUB_ENDPOINTS = [
    f"{workflow_host}:{workflow_port + 2 * i}" for i in range(N)
]
RESPONSE_ENDPOINTS = [
    f"{resp_host}:{resp_port + 2 * i}" for i in range(N)
]
RESPONSE_SUB_ENDPOINTS = RESPONSE_ENDPOINTS

# Roundrobin slot allocator
_slot_allocator = RoundRobinSlotAllocator(N)

FormatProcess = Literal["dict", "yaml", "pyflow"]

logger = setup_colored_logging(logging.INFO)


def extract_keep_alive(graph: Mapping[str, object]) -> bool:
    return bool(graph.get("keep_alive", False))

def debug_log_param_overrides_for_graph_dict(
    graph: ProcessGraph, log_path: str
) -> dict[str, dict[str, object]]:
    """Build ``unit_param_overrides`` for RunWorkflow so every **Debug** unit writes to ``log_path``.

    Without this, Debug falls back to ``workflow.log`` while the console grep uses
    ``get_debug_log_path()`` from settings — paths diverge after the user changes the setting.
    """
    lp = (log_path or "").strip()
    if not lp:
        return {}

    out: dict[str, dict[str, object]] = {}
    for u in graph.units:
        # if your canonical graph uses Unit.type == "Debug"
        if (u.type or "").strip() != "Debug":
            continue
        out[u.id] = {"log_path": lp}
    return out

def is_str_object_dict(x: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(x, dict):
        return False
    d = cast(dict[object, object], x)
    return all(isinstance(k, str) for k in d)

def _safe_repr_500(x: object) -> str:
    return repr(x)[:500]

def format_run_outputs(outputs: Mapping[str, object]) -> str:
    lines: list[str] = []

    for unit_id, port_values in sorted(outputs.items()):
        if not is_str_object_dict(port_values):
            lines.append(f"[{unit_id}] (non-dict output)")
            continue

        for port_name, value in sorted(port_values.items()):
            if value is None:
                s = "None"
            elif isinstance(value, str):
                s = value[:500] + ("..." if len(value) > 500 else "")
            elif isinstance(value, (dict, list)):
                try:
                    dumped = json.dumps(value, ensure_ascii=False)
                    s = dumped[:500] + ("..." if len(dumped) > 500 else "")
                except (TypeError, ValueError):
                    s = _safe_repr_500(cast(object, value))  # value is effectively Any/unknown; _safe_repr_500 handles object
            else:
                s = str(value)[:500]

            lines.append(f"  {unit_id}.{port_name}: {s}")

    return "\n".join(lines) if lines else "(no outputs)"


def build_initial_inputs_for_run(
    graph: ProcessGraph, user_message: str
) -> dict[str, dict[str, object]]:
    """Build initial_inputs for Inject units: each gets {'data': user_message} when non-empty.
    When empty, omit so Injects use params or Template connection."""
    initial: dict[str, dict[str, object]] = {}
    msg = (user_message or "").strip()
    if not msg:
        return initial
    for u in graph.units:
        if u.type == "Inject":
            initial[u.id] = {"data": msg}
    return initial


# --- publish graph job and await result (API: inputs, outputs only) ---

async def run_via_jobs_and_await(
    *,
    workflow_graph: ProcessGraph,
    initial_inputs: dict[str, object] | None,
    unit_param_overrides: dict[str, dict[str, object]] | None,
    format: str = "dict",
    keep_alive: bool,
    timeout_s: float | None,
) -> dict[str, object]:

    slot = await _slot_allocator.acquire()
    sub: ZmqSubscriber | None = None
    job_pub: ZmqPublisher | None = None

    try:
        run_id = uuid.uuid4().hex
        logger.info("Running workflow from Console (run_id=%s)", run_id)
        topics = ZmqTopics()

        sub = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=RESPONSE_SUB_ENDPOINTS[slot],
                topics=(
                    topics.token,
                    topics.result,
                    topics.error,
                    topics.update_batch,
                ),
                accept_topics=None,
                rcvtimeo_ms=200,
            )
        )

        final_outputs: dict[str, object] | None = None
        has_workflow_error = False
        workflow_error = ""

        async def _on_error(_topic: str, payload: dict[str, object]) -> None:
            nonlocal has_workflow_error, workflow_error
            if payload.get("run_id") != run_id:
                return
            err = payload.get("error")
            workflow_error = err if isinstance(err, str) else str(err)
            has_workflow_error = True
            logger.error(
                "Console: Received workflow error (run_id=%s, error=%s)",
                run_id,
                workflow_error,
            )

        async def _on_result(_topic: str, payload: dict[str, object]) -> None:
            nonlocal final_outputs
            if payload.get("run_id") != run_id:
                return

            outs = payload.get("outputs")
            if is_str_object_dict(outs):
                final_outputs = {k: outs[k] for k in outs}
            else:
                final_outputs = {}
            logger.info(
                "Console: Received workflow result (run_id=%s, keys=%s)",
                run_id,
                list(final_outputs.keys()),
            )

        async def _on_update_batch(_topic: str, payload: dict[str, object]) -> None:
            if payload.get("run_id") != run_id:
                return
            outs = payload.get("payload")
            if is_str_object_dict(outs):
                keys = list(outs.keys())
            else:
                keys = []
            logger.info(
                "Console: Received update_batch (run_id=%s, keys=%s)",
                run_id,
                keys,
            )

        async def _on_token(_topic: str, _payload: dict[str, object]) -> None:
            logger.info("Console: Received token (run_id=%s)", run_id)

        # Get subscribed for ZmqTopics
        sub.on(topics.error, _on_error)
        sub.on(topics.result, _on_result)
        sub.on(topics.update_batch, _on_update_batch)
        sub.on(topics.token, _on_token)

        job_pub = ZmqPublisher(
            pub_endpoint=JOB_PUB_ENDPOINTS[slot],
            topics=topics,
        )

        await asyncio.wait_for(sub.start(), timeout=30)
        logger.info("Console: Subscriber started (run_id=%s, slot=%s)", run_id, slot)

        job_pub.publish_job(
            run_id=run_id,
            workflow_graph=workflow_graph,
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format=format,
            keep_alive=keep_alive,
            response_endpoint=RESPONSE_ENDPOINTS[slot],
            execution_timeout_s=timeout_s,
        )
        logger.info(
            "Console: Published job (run_id=%s, keep_alive=%s, timeout_s=%s)",
            run_id,
            keep_alive,
            timeout_s,
        )

        start = time.monotonic()
        if keep_alive:
            logger.info(
                "Console: Waiting for final result with keep_alive enabled; no overall wait timeout (run_id=%s).",
                run_id,
            )
        else:
            logger.info(
                "Console: Waiting for final result; overall wait timeout=%s (run_id=%s).",
                timeout_s,
                run_id,
            )

        try:
            while final_outputs is None and not has_workflow_error:
                if (
                    (not keep_alive)
                    and (timeout_s is not None)
                    and (time.monotonic() - start) > timeout_s
                ):
                    logger.warning(
                        "Console: Overall wait timeout reached; stopping wait (run_id=%s, timeout_s=%s)",
                        run_id,
                        timeout_s,
                    )
                    raise WorkflowTimeoutError(timeout_s)

                await asyncio.sleep(0.01)

        except WorkflowTimeoutError:
            # Ensure we log the transition at the point of raising.
            logger.warning("Console: WorkflowTimeoutError raised (run_id=%s, timeout_s=%s)", run_id, timeout_s)
            raise
        finally:
            logger.info("Console: Stopping subscriber (run_id=%s)", run_id)
            await sub.stop()

        if has_workflow_error:
            logger.error("Console: Raising RuntimeError due to workflow error (run_id=%s)", run_id)
            raise RuntimeError(workflow_error)

        return final_outputs or {}

    finally:
        if sub is not None:
            try:
                await sub.stop()
            except (RuntimeError, ValueError, TypeError):
                logger.exception("Failed to stop subscriber")

        await _slot_allocator.release()
