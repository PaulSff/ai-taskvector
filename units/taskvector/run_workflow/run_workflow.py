"""RunWorkflow unit: run a workflow graph from parser action run_workflow, the current graph input, or (as a last resort) a workflow_path provided in unit params.

Accepts parser_output with optional run_workflow payload:
{ "path": "...", "initial_inputs": {...}, "unit_param_overrides": { "unit_id": { "param": value } } }.
When initial_inputs is set, it is merged into executor initial_inputs after Inject defaults
(e.g. rag_search for agents/tools/rag_search/rag_context_workflow.json, inject_path for rag/workflows/doc_to_text.json).
If path is set in the payload, loads the workflow from file; otherwise uses the graph input (current graph). If neither payload path nor graph is available, params["workflow_path"] may be used as a fallback.

Params: _needs_executor = true - MUST be set in params when the GraphExecutor injects the async loop/executor.
Streaming: status updates via params["_stream_callback"] using inline_status_stream_chunk.

ZMQ (optional): if unit params["zmq"] is present and contains job_pub_endpoint and response_sub_endpoint, this unit publishes a job to a workflow server and blocks until results are received. Internally, response_endpoint_for_job is set to the same value as response_sub_endpoint.
Example params["zmq"] object:
    "zmq": {
        "job_pub_endpoint": "tcp://127.0.0.1:5555",
        "response_sub_endpoint": "tcp://127.0.0.1:5556",
      },
      "execution_timeout_s": 30,
    }

TODO: implement keep_alive mode (keep_alive: bool param)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable, Mapping
from typing import cast

from core.normalizer import get_process_graph_from_any
from core.normalizer.shared import (
    as_workflow_inputs,
    workflow_inputs_to_json_object,
)
from core.schemas.primitives import (
    FormatProcess,
    JsonObject,
    WorkflowInputs,
    WorkflowOutputs,
    is_format_process,
    is_json_object,
)
from core.schemas.process_graph import ProcessGraph, Unit
from runtime.executor import GraphStreamCallback
from runtime.run import run_workflow as run_workflow_inline
from runtime.stream_ui_signals import inline_status_stream_chunk
from services.zmq import (
    ZmqPublishConfig,
    ZmqPublisher,
    ZmqSubscriber,
    ZmqSubscriptionConfig,
    ZmqTopics,
)
from units.registry import UnitSpec, register_unit

RUN_WORKFLOW_INPUT_PORTS = [
    ("parser_output", "Any"),
    ("graph", "ProcessGraph"),
]
RUN_WORKFLOW_OUTPUT_PORTS = [
    ("data", "JsonObject"),
    ("error", "str")
]

DEFAULT_EXECUTION_TIMEOUT_S = 120.0
AWAIT_EXECUTION_EXPIRED_TIMEOUT_S = 6.0


def _build_initial_inputs(
    graph: ProcessGraph,
    user_message: str,
) -> WorkflowInputs:
    initial: WorkflowInputs = {}
    msg = user_message.strip()

    graph_dict: JsonObject = graph.model_dump(mode="json")

    for unit in graph.units:
        if unit.type != "Inject":
            continue

        if unit.id == "inject_graph":
            initial[unit.id] = {"data": graph_dict}
        elif msg:
            initial[unit.id] = {"data": msg}

    return initial


def _apply_unit_param_overrides(
    graph: ProcessGraph,
    overrides: WorkflowInputs | None,
) -> ProcessGraph:
    if overrides is None:
        return graph

    new_units: list[Unit] = []

    for unit in graph.units:
        override_value = overrides.get(unit.id)

        if override_value is None:
            new_units.append(unit)
            continue

        current_params: JsonObject = (
            unit.params if is_json_object(unit.params) else {}
        )

        merged_params: JsonObject = {
            **current_params,
            **override_value,
        }

        new_units.append(
            unit.model_copy(update={"params": merged_params})
        )

    return graph.model_copy(update={"units": new_units})


def _merge_payload_initial_inputs(
    initial: WorkflowInputs,
    payload: JsonObject,
) -> WorkflowInputs:
    extra = payload.get("initial_inputs")

    if not is_json_object(extra):
        return initial

    merged: WorkflowInputs = dict(initial)

    for unit_id, ports_value in extra.items():
        if not unit_id.strip():
            continue

        if not is_json_object(ports_value):
            continue

        previous = merged.get(unit_id)

        if isinstance(previous, dict):
            merged[unit_id] = {
                **previous,
                **ports_value,
            }
        else:
            merged[unit_id] = dict(ports_value)

    return merged


async def _publish_and_wait_zmq(
    *,
    workflow_path: str | None,
    workflow_graph: ProcessGraph | None,
    initial_inputs: WorkflowInputs | None = None,
    unit_param_overrides: WorkflowInputs | None = None,
    stream_cb: GraphStreamCallback| None = None,
    format: str | None,
    publish_config: ZmqPublishConfig,
    subscription_config: ZmqSubscriptionConfig,
) -> WorkflowOutputs:
    run_id = uuid.uuid4().hex

    topics = ZmqTopics()

    job_pub = ZmqPublisher(
        pub_endpoint=publish_config.pub_endpoint,
        topics=topics,
    )

    sub = ZmqSubscriber(
        config=ZmqSubscriptionConfig(
            sub_endpoint=subscription_config.sub_endpoint,
            topics=(topics.token, topics.result, topics.error),
            accept_topics=subscription_config.accept_topics,
            rcvtimeo_ms=subscription_config.rcvtimeo_ms,
            max_in_flight_handlers=subscription_config.max_in_flight_handlers,
        )
    )

    final_outputs: JsonObject | None = None
    has_err = False
    err_msg = ""

    async def _on_error(
        _topic: str,
        payload: JsonObject,
    ) -> None:
        nonlocal has_err, err_msg

        if payload.get("run_id") != run_id:
            return

        error = payload.get("error")
        err_msg = error if isinstance(error, str) else str(error)
        has_err = True

    async def _on_result(
        _topic: str,
        payload: JsonObject,
    ) -> None:
        nonlocal final_outputs

        if payload.get("run_id") != run_id:
            return

        outputs = payload.get("outputs")
        final_outputs = outputs if isinstance(outputs, dict) else {}

    async def _on_token(
        _topic: str,
        payload: JsonObject,
    ) -> None:
        if stream_cb is None:
            return

        if payload.get("run_id") != run_id:
            return

        token = payload.get("token")

        if not isinstance(token, str):
            return

        try:
            stream_cb(token)
        except (TypeError, RuntimeError):
            pass

    sub.on(topics.error, _on_error)
    sub.on(topics.result, _on_result)
    sub.on(topics.token, _on_token)

    execution_timeout_s = publish_config.execution_timeout_s

    await asyncio.wait_for(
        sub.start(),
        timeout=execution_timeout_s + AWAIT_EXECUTION_EXPIRED_TIMEOUT_S,
    )

    try:
        job_pub.publish_job(
            run_id=run_id,
            workflow_path=workflow_path,
            workflow_graph=workflow_graph,
            format = format,
            initial_inputs=workflow_inputs_to_json_object(initial_inputs),
            unit_param_overrides=workflow_inputs_to_json_object(
                    unit_param_overrides
                ),
            response_endpoint=publish_config.response_endpoint,
            update_endpoint=publish_config.update_endpoint,
            execution_timeout_s=execution_timeout_s,
        )

        start = time.monotonic()

        while final_outputs is None and not has_err:
            if (
                execution_timeout_s > 0
                and time.monotonic() - start > execution_timeout_s
            ):
                raise TimeoutError(
                    f"Workflow execution timed out after {execution_timeout_s}s"
                )

            await asyncio.sleep(0.01)

        if has_err:
            raise RuntimeError(err_msg)

        return final_outputs or {}

    finally:
        await sub.stop()


def _maybe_get_zmq_params(
    params: Mapping[str, object],
    execution_timeout_s: float | None,
) -> ZmqPublishConfig | None:
    pub_endpoint = params.get("job_pub_endpoint")
    response_endpoint = params.get("response_sub_endpoint")
    update_endpoint = params.get("update_endpoint")

    if not isinstance(pub_endpoint, str):
        return None

    if not isinstance(response_endpoint, str):
        return None

    if not isinstance(update_endpoint, str):
        return None

    return ZmqPublishConfig(
        pub_endpoint=pub_endpoint,
        response_endpoint=response_endpoint,
        update_endpoint=update_endpoint,
        execution_timeout_s=(
            execution_timeout_s
            if execution_timeout_s is not None
            else DEFAULT_EXECUTION_TIMEOUT_S
        ),
    )


def _get_background_loop(
    params: dict[str, object],
) -> asyncio.AbstractEventLoop:
    executor = params.get("_executor")

    background_loop = (
        getattr(executor, "_loop", None)
        if executor is not None
        else None
    )

    if background_loop is None:
        background_loop = (
            params.get("_executor_loop")
            or params.get("_background_loop")
        )

    if not isinstance(background_loop, asyncio.AbstractEventLoop):
        raise TypeError(
            "run_workflow: background event loop not provided"
        )

    if not background_loop.is_running():
        raise RuntimeError(
            "run_workflow: background event loop is not running"
        )

    return background_loop


def _run_workflow_step(
    params: dict[str, object],
    inputs: dict[str, object],
    state: dict[str, object],
    dt: float,
) -> tuple[dict[str, object], dict[str, object]]:
    del dt

    parser_output = inputs.get("parser_output")
    graph_input = inputs.get("graph")

    if not is_json_object(parser_output):
        return {"data": {}, "error": ""}, state

    payload_value = parser_output.get("run_workflow")

    if not is_json_object(payload_value):
        return {"data": {}, "error": ""}, state

    payload = payload_value

    stream_value = params.get("_stream_callback")

    stream_callback: GraphStreamCallback | None = None

    if callable(stream_value):
        callback = cast(
            Callable[[str], object],
            stream_value,
        )

        def stream_callback_wrapper(token: str) -> None:
            _ = callback(token)

        stream_callback = stream_callback_wrapper

    if stream_callback is not None:
        try:
            stream_callback(
                inline_status_stream_chunk("Thinking…")
            )
        except (TypeError, RuntimeError):
            pass

    try:
        path_value = payload.get("path")

        workflow_path = (
            path_value.strip()
            if isinstance(path_value, str) and path_value.strip()
            else None
        )

        if workflow_path is None:
            fallback_value = params.get("workflow_path")
            workflow_path = (
                fallback_value.strip()
                if (
                    isinstance(fallback_value, str)
                    and fallback_value.strip()
                )
                else None
            )

        graph: ProcessGraph | None = None

        if workflow_path is not None:
            from pathlib import Path

            from core.normalizer import load_process_graph_from_file

            graph = load_process_graph_from_file(
                Path(workflow_path).expanduser().resolve(),
                format="dict",
            )
        elif graph_input is not None:
            graph = get_process_graph_from_any(graph_input)
        else:
            return {
                "data": {},
                "error": (
                    "run_workflow: no path and no graph "
                    "inputs available"
                ),
            }, state

        unit_param_overrides = as_workflow_inputs(
            payload.get("unit_param_overrides"),
        )

        graph = _apply_unit_param_overrides(
            graph,
            unit_param_overrides,
        )

        raw_user_message = params.get("user_message")
        user_message = (
            raw_user_message.strip()
            if isinstance(raw_user_message, str)
            else ""
        )

        initial_inputs = _build_initial_inputs(
            graph,
            user_message,
        )
        initial_inputs = _merge_payload_initial_inputs(
            initial_inputs,
            payload,
        )

        format_value = payload.get("format")

        output_format: FormatProcess | None = (
            format_value
            if is_format_process(format_value)
            else None
        )

        timeout_value = params.get(
            "execution_timeout_s",
            DEFAULT_EXECUTION_TIMEOUT_S,
        )

        if timeout_value is None:
            execution_timeout_s: float | None = None
        elif isinstance(timeout_value, (str, int, float)):
            try:
                execution_timeout_s = float(timeout_value)
            except (TypeError, ValueError):
                execution_timeout_s = DEFAULT_EXECUTION_TIMEOUT_S
        else:
            execution_timeout_s = DEFAULT_EXECUTION_TIMEOUT_S


        zmq_params = _maybe_get_zmq_params(
            params,
            execution_timeout_s,
        )

        if zmq_params is not None:
            topics = ZmqTopics()

            publish_config = zmq_params

            subscription_config = ZmqSubscriptionConfig(
                sub_endpoint=zmq_params.response_endpoint,
                topics=(
                    topics.token,
                    topics.result,
                    topics.error,
                ),
            )

            async def _run_zmq() -> JsonObject:
                return await _publish_and_wait_zmq(
                    workflow_path=workflow_path,
                    workflow_graph=(
                        graph
                        if workflow_path is None
                        else None
                    ),
                    initial_inputs=initial_inputs,
                    unit_param_overrides=(
                        unit_param_overrides
                    ),
                    stream_cb=(
                        stream_callback
                        if callable(stream_callback)
                        else None
                    ),
                    format=output_format,
                    publish_config=publish_config,
                    subscription_config=subscription_config,
                )

            background_loop = _get_background_loop(params)

            future = asyncio.run_coroutine_threadsafe(
                _run_zmq(),
                background_loop,
            )

            wait_timeout = (
                execution_timeout_s
                if execution_timeout_s is not None
                else DEFAULT_EXECUTION_TIMEOUT_S
            )

            outputs = future.result(
                timeout=(
                    wait_timeout
                    + AWAIT_EXECUTION_EXPIRED_TIMEOUT_S
                )
            )

        else:
            outputs = run_workflow_inline(
                workflow_path=workflow_path,
                workflow_graph=(
                    graph
                    if workflow_path is None
                    else None
                ),
                initial_inputs=initial_inputs,
                unit_param_overrides=unit_param_overrides,
                format=output_format,
                execution_timeout_s=execution_timeout_s,
                stream_callback=(
                    stream_callback
                    if callable(stream_callback)
                    else None
                ),
                run_id=None,
                zmq_publisher=None,
                send_job_message=False,
            )

        return {
            "data": outputs,
            "error": "",
        }, state

    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        TimeoutError,
    ) as exc:
        return {
            "data": {},
            "error": f"run_workflow execute failed: {exc}",
        }, state


def register_run_workflow() -> None:
    register_unit(
        UnitSpec(
            type_name="RunWorkflow",
            input_ports=RUN_WORKFLOW_INPUT_PORTS,
            output_ports=RUN_WORKFLOW_OUTPUT_PORTS,
            step_fn=_run_workflow_step,
            environment_tags=["taskvector"],
            environment_tags_are_agnostic=False,
            description=(
                "Wrapper that preserves RunWorkflow payload semantics. "
                "If payload.path is set, loads the workflow from file; otherwise uses "
                "the graph input (current graph). If unit params.zmq is set, publishes "
                "job to workflow server and awaits results via ZMQ."
            ),
        )
    )


__all__ = [
    "RUN_WORKFLOW_INPUT_PORTS",
    "RUN_WORKFLOW_OUTPUT_PORTS",
    "register_run_workflow",
]
