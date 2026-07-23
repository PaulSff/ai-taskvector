from __future__ import annotations

import asyncio
import re
import time
import uuid
from pathlib import Path
from typing import Any, Literal, Optional

from gui.chat.utils import collect_workflow_errors
from runtime import ZmqPublisher, ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics
from runtime.run import WorkflowTimeoutError
from gui.components.settings import (
    get_tools_workflows_job_pub_endpoint,
    get_tools_workflows_response_endpoint,
    get_tools_workflows_max_concurrent_calls,
)
from .paths import DEFAULT_EXECUTION_TIMEOUT_S

# Keep your existing constants/endpoints (base endpoints)
JOB_PUB_ENDPOINT = get_tools_workflows_job_pub_endpoint()
RESULT_SUB_ENDPOINT = get_tools_workflows_response_endpoint()
RESPONSE_PUB_ENDPOINT = RESULT_SUB_ENDPOINT

FormatProcess = Literal["dict", "yaml", "pyflow"]


def _parse_host_port(endpoint: str) -> tuple[str, int]:
    # "tcp://127.0.0.1:6679" -> ("tcp://127.0.0.1", 6679)
    m = re.match(r"^(.*):(\d+)$", endpoint)
    if not m:
        raise ValueError(f"Unexpected endpoint format: {endpoint}")
    return m.group(1), int(m.group(2))


N = get_tools_workflows_max_concurrent_calls()

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


def _missing_workflow_msg(path: Path) -> str:
    return f"Required workflow file not found: {path}"


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


async def run_workflow_with_errors(
    path: str | Path,
    initial_inputs: dict[str, dict[str, Any]] | None = None,
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    format: "FormatProcess | None" = "dict",
    execution_timeout_s: float | None = None,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """
    Pure async version: publishes the job over the workflow server and
    waits for subscribed response.

    Returns (outputs, errors) where errors are collected from outputs.
    execution_timeout_s: if set, abort after this many seconds (raises WorkflowTimeoutError).
    """

    initial_inputs = initial_inputs or {}
    wp = Path(path).resolve()

    # Slot allocation wraps the whole publish+wait lifecycle
    slot = await _acquire_slot()
    sub: Optional[ZmqSubscriber] = None
    job_pub: Optional[ZmqPublisher] = None

    try:
        if not wp.exists():
            raise FileNotFoundError(_missing_workflow_msg(wp))

        run_id = uuid.uuid4().hex
        topics = ZmqTopics()

        sub = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=RESPONSE_SUB_ENDPOINTS[slot],
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

        async def _on_token(_topic: str, payload: dict[str, Any]) -> None:
            # Token stream not needed here; handler kept to consume it if server publishes.
            return

        sub.on(topics.token, _on_token)
        sub.on(topics.result, _on_result)
        sub.on(topics.error, _on_error)

        job_pub = ZmqPublisher(pub_endpoint=JOB_PUB_ENDPOINTS[slot], topics=ZmqTopics())

        await asyncio.wait_for(sub.start(), timeout=DEFAULT_EXECUTION_TIMEOUT_S)

        job_pub.publish_job(
            run_id=run_id,
            workflow_path=str(wp),
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format=format,
            response_endpoint=RESPONSE_ENDPOINTS[slot],
        )

        start = time.monotonic()
        try:
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
        return outputs, collect_workflow_errors(outputs)

    finally:
        # Ensure the slot is always returned even on timeout or publish/start errors
        if sub is not None:
            try:
                # If an exception happened before sub.start(), sub.stop() may be harmless,
                # but we still guard to avoid masking the real error.
                await sub.stop()
            except Exception:
                pass
        await _release_slot()
