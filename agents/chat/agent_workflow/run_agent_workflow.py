from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from agents.chat.agent_workflow.collect_workflow_response import (
    merge_response_from_workflow_outputs,
)
from agents.chat.agent_workflow.wf_response_schema import AgentWorkflowResponse
from core.normalizer.shared import workflow_inputs_to_json_object
from core.schemas.primitives import (
    FormatProcess,
    JsonObject,
    WorkflowInputs,
    WorkflowOutputs,
)
from config.settings import (
    get_agents_workflows_job_pub_endpoint,
    get_agents_workflows_max_concurrent_calls,
    get_agents_workflows_response_endpoint,
)
from runtime.executor import GraphStreamCallback
from runtime.run import WorkflowTimeoutError
from services.server import (
    RoundRobinSlotAllocator,
    _parse_host_port,
)
from services.zmq import ZmqPublisher, ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics

from .helpers import missing_workflow_msg
from .paths import DEFAULT_EXECUTION_TIMEOUT_S, agent_WORKFLOW_PATH

# ---- fixed endpoint pools (configure N >= max concurrent calls) ----
WORKFLOW_SERVER_ENDPOINT = get_agents_workflows_job_pub_endpoint()  # e.g. tcp://127.0.0.1:6679
CORE_WORKFLOWS_RESPONSE_ENDPOINT = get_agents_workflows_response_endpoint()  # e.g. tcp://127.0.0.1:xxxx
N = get_agents_workflows_max_concurrent_calls()

workflow_host, workflow_port = _parse_host_port(WORKFLOW_SERVER_ENDPOINT)
resp_host, resp_port = _parse_host_port(CORE_WORKFLOWS_RESPONSE_ENDPOINT)

# ---- fixed endpoint pools (configure N >= max concurrent calls) ----
JOB_PUB_ENDPOINTS = [f"{workflow_host}:{workflow_port + 2 * i}" for i in range(N)]
RESPONSE_ENDPOINTS = [f"{resp_host}:{resp_port + 2 * i}" for i in range(N)]
RESPONSE_SUB_ENDPOINTS = RESPONSE_ENDPOINTS

# Roundrobin slot allocator
_slot_allocator = RoundRobinSlotAllocator(N)

# ---- Publish workflow job to the server ---

async def _publish_and_wait(
    wp: Path,
    initial_inputs: WorkflowInputs | None = None,
    unit_param_overrides: WorkflowInputs | None = None,
    *,
    execution_timeout_s: float | None,
    stream_callback: Callable[[str], None] | None,
    format: FormatProcess = "dict",
) -> WorkflowOutputs:
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
                topics=(topics.token, topics.result, topics.error),
                accept_topics=None,
                rcvtimeo_ms=200,
            )
        )

        has_workflow_error = False
        workflow_error = ""
        final_outputs: JsonObject | None = None

        async def _on_error(_topic: str, payload: JsonObject) -> None:
            nonlocal has_workflow_error, workflow_error
            if payload.get("run_id") != run_id:
                return
            err = payload.get("error")
            workflow_error = err if isinstance(err, str) else str(err)
            has_workflow_error = True

        async def _on_result(_topic: str, payload: JsonObject) -> None:
            nonlocal final_outputs
            if payload.get("run_id") != run_id:
                return
            outs = payload.get("outputs")
            if isinstance(outs, dict):
                final_outputs = outs

        async def _on_token(_topic: str, payload: JsonObject) -> None:
            if payload.get("run_id") != run_id:
                return
            tok = payload.get("token")
            if isinstance(tok, str) and stream_callback is not None:
                stream_callback(tok)

        sub.on(topics.token, _on_token)
        sub.on(topics.result, _on_result)
        sub.on(topics.error, _on_error)

        job_pub = ZmqPublisher(pub_endpoint=JOB_PUB_ENDPOINTS[slot], topics=ZmqTopics())
        start = time.monotonic()

        await asyncio.wait_for(sub.start(), timeout=30)

        job_pub.publish_job(
            run_id=run_id,
            workflow_path=str(wp),
            initial_inputs = workflow_inputs_to_json_object(initial_inputs),
            unit_param_overrides=workflow_inputs_to_json_object(
                unit_param_overrides
            ),
            format=format,
            response_endpoint=RESPONSE_ENDPOINTS[slot],
        )

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

        return final_outputs or {}

    finally:
        # Always release the round-robin slot
        await _slot_allocator.release()



async def run_agent_workflow(
    initial_inputs: WorkflowInputs | None = None,
    unit_param_overrides: WorkflowInputs | None = None,
    execution_timeout_s: float | None = DEFAULT_EXECUTION_TIMEOUT_S,
    stream_callback: GraphStreamCallback| None = None,
    *,
    workflow_path: str | Path | None = None,
) -> AgentWorkflowResponse:
    print(
        "[run_agent_workflow] called: initial_inputs=%s unit_param_overrides=%s execution_timeout_s=%s stream_callback=%s workflow_path=%s",
        type(initial_inputs),
        type(unit_param_overrides),
        execution_timeout_s,
        getattr(stream_callback, "__name__", None)
        if stream_callback is not None
        else None,
        str(workflow_path) if workflow_path is not None else None,
    )

    wp = (
        Path(workflow_path).resolve()
        if workflow_path is not None
        else agent_WORKFLOW_PATH
    )

    outputs = await _publish_and_wait(
        wp,
        initial_inputs,
        unit_param_overrides,
        execution_timeout_s=execution_timeout_s,
        stream_callback=stream_callback,
        format="dict",
    )

    return merge_response_from_workflow_outputs(outputs)
