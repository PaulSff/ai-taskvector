from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path

from agents.chat.agent_workflow.collect_workflow_response import collect_workflow_errors
from core.normalizer.shared import workflow_inputs_to_json_object
from core.schemas.primitives import (
    FormatProcess,
    JsonObject,
    WorkflowErrors,
    WorkflowInputs,
    WorkflowOutputs,
    is_json_object,
)
from gui.components.settings import (
    get_tools_workflows_job_pub_endpoint,
    get_tools_workflows_max_concurrent_calls,
    get_tools_workflows_response_endpoint,
)
from runtime.run import WorkflowTimeoutError
from services.server import (
    RoundRobinSlotAllocator,
    _parse_host_port,
)
from services.zmq import ZmqPublisher, ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics

from .helpers import missing_workflow_msg
from .paths import DEFAULT_EXECUTION_TIMEOUT_S

# base endpoints
JOB_PUB_ENDPOINT = get_tools_workflows_job_pub_endpoint()
RESULT_SUB_ENDPOINT = get_tools_workflows_response_endpoint()
RESPONSE_PUB_ENDPOINT = RESULT_SUB_ENDPOINT

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

# Roundrobin slot allocator
_slot_allocator = RoundRobinSlotAllocator(N)

logger = logging.getLogger(__name__)

# ---- Publish workflow job to the server ---

async def run_workflow_with_errors(
    path: str | Path,
    initial_inputs: WorkflowInputs | None = None,
    unit_param_overrides: WorkflowInputs | None = None,
    format: FormatProcess | None = "dict",
    execution_timeout_s: float | None = None,
) -> tuple[WorkflowOutputs, WorkflowErrors]:
    """
    Pure async version: publishes the job over the workflow server and
    waits for the subscribed response.

    Returns (outputs, errors), where errors are collected from outputs.

    execution_timeout_s:
        If set, abort after this many seconds by raising
        WorkflowTimeoutError.
    """

    initial_inputs = initial_inputs or {}
    wp = Path(path).resolve()

    slot = await _slot_allocator.acquire()

    sub: ZmqSubscriber | None = None
    job_pub: ZmqPublisher | None = None

    try:
        if not wp.exists():
            raise FileNotFoundError(missing_workflow_msg(wp))

        run_id = uuid.uuid4().hex
        topics = ZmqTopics()

        sub = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=RESPONSE_SUB_ENDPOINTS[slot],
                topics=(
                    topics.token,
                    topics.result,
                    topics.error,
                ),
                accept_topics=None,
                rcvtimeo_ms=200,
            )
        )

        has_workflow_error = False
        workflow_error = ""
        final_outputs: WorkflowOutputs | None = None

        async def _on_error(
            _topic: str,
            payload: JsonObject,
        ) -> None:
            nonlocal has_workflow_error, workflow_error

            if payload.get("run_id") != run_id:
                return

            err = payload.get("error")
            workflow_error = (
                err if isinstance(err, str) else str(err)
            )
            has_workflow_error = True

        async def _on_result(
            _topic: str,
            payload: JsonObject,
        ) -> None:
            nonlocal final_outputs

            if payload.get("run_id") != run_id:
                return

            outputs = payload.get("outputs")

            if is_json_object(outputs):
                final_outputs = outputs
            else:
                final_outputs = {}

        async def _on_token(
            _topic: str,
            payload: JsonObject,
        ) -> None:
            # Token streaming is not needed here.
            return

        sub.on(topics.token, _on_token)
        sub.on(topics.result, _on_result)
        sub.on(topics.error, _on_error)

        job_pub = ZmqPublisher(
            pub_endpoint=JOB_PUB_ENDPOINTS[slot],
            topics=ZmqTopics(),
        )

        await asyncio.wait_for(
            sub.start(),
            timeout=DEFAULT_EXECUTION_TIMEOUT_S,
        )

        job_pub.publish_job(
            run_id=run_id,
            workflow_path=str(wp),
            initial_inputs=workflow_inputs_to_json_object(
                initial_inputs
            ),
            unit_param_overrides=(
                workflow_inputs_to_json_object(
                    unit_param_overrides
                )
                if unit_param_overrides is not None
                else {}
            ),
            format=format,
            response_endpoint=RESPONSE_ENDPOINTS[slot],
        )

        start = time.monotonic()

        try:
            while (
                final_outputs is None
                and not has_workflow_error
            ):
                if (
                    execution_timeout_s is not None
                    and time.monotonic() - start
                    > execution_timeout_s
                ):
                    raise WorkflowTimeoutError(
                        execution_timeout_s
                    )

                await asyncio.sleep(0.01)

        finally:
            await sub.stop()

        if has_workflow_error:
            raise RuntimeError(workflow_error)

        outputs: WorkflowOutputs = (
            final_outputs if final_outputs is not None else {}
        )

        return outputs, collect_workflow_errors(outputs)

    finally:
        if sub is not None:
            try:
                await sub.stop()
            except (TypeError, AttributeError):
                logger.exception(
                    "Failed to stop subscriber"
                )

        await _slot_allocator.release()
