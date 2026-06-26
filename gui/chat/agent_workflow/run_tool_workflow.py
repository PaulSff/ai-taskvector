from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, Literal, Optional

from gui.chat.utils import collect_workflow_errors
from runtime import ZmqPublisher, ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics
from runtime.run import WorkflowTimeoutError

# Keep your existing constants/endpoints
JOB_PUB_ENDPOINT = "tcp://127.0.0.1:6663"
RESULT_SUB_ENDPOINT = "tcp://127.0.0.1:6673"
RESPONSE_PUB_ENDPOINT = RESULT_SUB_ENDPOINT  # as you stated

FormatProcess = Literal["dict", "yaml", "pyflow"]


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

    # Token stream not needed here; handler kept to consume it if server publishes.
    async def _on_token(_topic: str, payload: dict[str, Any]) -> None:
        return

    sub.on(topics.token, _on_token)
    sub.on(topics.result, _on_result)
    sub.on(topics.error, _on_error)

    await asyncio.wait_for(sub.start(), timeout=30)

    job_pub.publish_job(
        run_id=run_id,
        workflow_path=str(wp),
        initial_inputs=initial_inputs,
        unit_param_overrides=unit_param_overrides,
        format=format,
        response_endpoint=RESPONSE_PUB_ENDPOINT,
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
