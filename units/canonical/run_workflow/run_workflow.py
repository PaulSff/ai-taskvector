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
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, cast

from core.schemas.process_graph import ProcessGraph
from runtime import (
    ZmqPublisher,
    ZmqSubscriber,
    ZmqSubscriptionConfig,
    ZmqTopics,
)
from runtime.run import run_workflow as run_workflow_inline
from runtime.stream_ui_signals import inline_status_stream_chunk
from units.registry import UnitSpec, register_unit

RUN_WORKFLOW_INPUT_PORTS = [
    ("parser_output", "Any"),
    ("graph", "Any"),
]
RUN_WORKFLOW_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]

DEFAULT_EXECUTION_TIMEOUT_S = 120.0
AWAIT_EXECUTION_EXPIRED_TIMEOUT_S = 6.0


def _get_process_graph_from_any(g: Any) -> ProcessGraph:
    from core.normalizer import to_process_graph

    if g is None:
        raise TypeError("graph missing")

    if isinstance(g, ProcessGraph):
        return g
    if isinstance(g, dict):
        return to_process_graph(g, format="dict")
    if hasattr(g, "model_dump"):
        return to_process_graph(g.model_dump(by_alias=True), format="dict")
    raise TypeError("graph input must be dict or ProcessGraph")


def _build_initial_inputs(
    graph: ProcessGraph, user_message: str
) -> dict[str, dict[str, Any]]:
    initial: dict[str, dict[str, Any]] = {}
    msg = (user_message or "").strip()
    graph_dict: dict[str, Any] = (
        graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else {}
    )
    for u in graph.units:
        if u.type == "Inject":
            if u.id == "inject_graph":
                initial[u.id] = {"data": graph_dict}
            elif msg:
                initial[u.id] = {"data": msg}
    return initial


def _apply_unit_param_overrides(graph: ProcessGraph, overrides: Any) -> ProcessGraph:
    if not overrides or not isinstance(overrides, dict):
        return graph
    new_units = []
    for u in graph.units:
        over = overrides.get(u.id)
        if over and isinstance(over, dict):
            new_units.append(
                u.model_copy(update={"params": {**(u.params or {}), **over}})
            )
        else:
            new_units.append(u)
    return graph.model_copy(update={"units": new_units})


def _merge_payload_initial_inputs(
    initial: dict[str, dict[str, Any]],
    payload: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    extra = payload.get("initial_inputs")
    if not isinstance(extra, dict):
        return initial
    merged = dict(initial)
    for uid, ports in extra.items():
        if not isinstance(uid, str) or not uid.strip():
            continue
        if not isinstance(ports, dict):
            continue
        prev = merged.get(uid)
        if isinstance(prev, dict):
            merged[uid] = {**prev, **ports}
        else:
            merged[uid] = dict(ports)
    return merged


async def _publish_and_wait_zmq(
    *,
    workflow_path: str | None,
    workflow_graph: ProcessGraph | None,
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None,
    stream_cb: Any,
    format: str | None,
    execution_timeout_s: float | None,
    zmq: dict[str, Any],
) -> dict[str, Any]:
    run_id = uuid.uuid4().hex

    topics = ZmqTopics()
    job_pub = ZmqPublisher(
        pub_endpoint=zmq["job_pub_endpoint"],
        topics=topics,
    )

    resp_endpoint = zmq["response_sub_endpoint"]
    sub = ZmqSubscriber(
        config=ZmqSubscriptionConfig(
            sub_endpoint=resp_endpoint,
            topics=(topics.token, topics.result, topics.error),
            accept_topics=None,
            rcvtimeo_ms=200,
        )
    )

    final_outputs: dict[str, Any] | None = None
    has_err = False
    err_msg = ""

    async def _on_error(_topic: str, payload: dict[str, Any]) -> None:
        nonlocal has_err, err_msg
        if payload.get("run_id") != run_id:
            return
        e = payload.get("error")
        err_msg = e if isinstance(e, str) else str(e)
        has_err = True

    async def _on_result(_topic: str, payload: dict[str, Any]) -> None:
        nonlocal final_outputs
        if payload.get("run_id") != run_id:
            return
        outs = payload.get("outputs")
        final_outputs = outs if isinstance(outs, dict) else {}

    async def _on_token(_topic: str, payload: dict[str, Any]) -> None:
        if stream_cb is None:
            return
        if payload.get("run_id") != run_id:
            return
        tok = payload.get("token")
        if isinstance(tok, str):
            try:
                stream_cb(tok)
            except Exception:
                pass

    sub.on(topics.error, _on_error)
    sub.on(topics.result, _on_result)
    sub.on(topics.token, _on_token)

    await asyncio.wait_for(
        sub.start(),
        timeout=execution_timeout_s + AWAIT_EXECUTION_EXPIRED_TIMEOUT_S
        if execution_timeout_s is not None
        else DEFAULT_EXECUTION_TIMEOUT_S,
    )

    try:
        if workflow_path:
            job_pub.publish_job(
                run_id=run_id,
                workflow_path=workflow_path,
                initial_inputs=initial_inputs,
                unit_param_overrides=unit_param_overrides or {},
                format=format,
                response_endpoint=zmq["response_endpoint_for_job"],
                execution_timeout_s=execution_timeout_s,
            )
        else:
            job_pub.publish_job(
                run_id=run_id,
                workflow_graph=(
                    workflow_graph.model_dump(by_alias=True)
                    if workflow_graph is not None
                    and hasattr(workflow_graph, "model_dump")
                    else (workflow_graph if isinstance(workflow_graph, dict) else None)
                ),
                initial_inputs=initial_inputs,
                unit_param_overrides=unit_param_overrides or {},
                format=format,
                response_endpoint=zmq["response_endpoint_for_job"],
                execution_timeout_s=execution_timeout_s,
            )

        import time

        start = time.monotonic()
        while final_outputs is None and not has_err:
            if execution_timeout_s is not None and execution_timeout_s > 0:
                if (time.monotonic() - start) > execution_timeout_s:
                    raise TimeoutError(
                        f"Workflow execution timed out after {execution_timeout_s}s"
                    )
            await asyncio.sleep(0.01)

        if has_err:
            raise RuntimeError(err_msg)

        return final_outputs or {}
    finally:
        await sub.stop()


def _maybe_get_zmq_params(params: dict[str, Any]) -> dict[str, Any] | None:
    zmq = params.get("zmq")
    if isinstance(zmq, dict):
        required = {
            "job_pub_endpoint",
            "response_sub_endpoint",
        }
        if required.issubset(set(zmq.keys())):
            return zmq
    return None


def _run_workflow_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    parser_output = inputs.get("parser_output")
    graph_input = inputs.get("graph")

    user_message = (params.get("user_message") or "").strip() or ""

    if not isinstance(parser_output, dict) or "run_workflow" not in parser_output:
        return ({"data": {}, "error": ""}, state)

    payload = parser_output.get("run_workflow")
    if not isinstance(payload, dict):
        return ({"data": {}, "error": ""}, state)

    stream_cb = params.get("_stream_callback")

    if callable(stream_cb):
        try:
            stream_cb(inline_status_stream_chunk("Thinking…"))
        except Exception:
            pass

    try:
        path_val = payload.get("path")
        workflow_path = (
            path_val.strip() if isinstance(path_val, str) and path_val.strip() else None
        )

        if workflow_path is None:
            p2 = params.get("workflow_path")
            workflow_path = p2.strip() if isinstance(p2, str) and p2.strip() else None

        unit_param_overrides = payload.get("unit_param_overrides")
        if unit_param_overrides is not None and not isinstance(
            unit_param_overrides, dict
        ):
            unit_param_overrides = None

        graph: ProcessGraph | None = None
        if workflow_path:
            from pathlib import Path

            from core.normalizer import load_process_graph_from_file

            p = Path(workflow_path).expanduser().resolve()
            graph = load_process_graph_from_file(p, format="dict")
        else:
            if graph_input is None:
                return (
                    {
                        "data": {},
                        "error": "run_workflow: no path and no graph inputs available",
                    },
                    state,
                )
            graph = _get_process_graph_from_any(graph_input)

        assert graph is not None
        graph = _apply_unit_param_overrides(graph, unit_param_overrides)

        initial_inputs = _build_initial_inputs(graph, user_message)
        initial_inputs = _merge_payload_initial_inputs(initial_inputs, payload)

        fmt = payload.get("format") if isinstance(payload.get("format"), str) else None

        execution_timeout_s = params.get(
            "execution_timeout_s", DEFAULT_EXECUTION_TIMEOUT_S
        )
        if execution_timeout_s is not None:
            try:
                execution_timeout_s = float(execution_timeout_s)
            except Exception:
                execution_timeout_s = None

        zmq_cfg = _maybe_get_zmq_params(params)
        if zmq_cfg is not None:
            zmq_cfg = dict(zmq_cfg)
            zmq_cfg["response_endpoint_for_job"] = zmq_cfg["response_sub_endpoint"]

            async def _go() -> dict[str, Any]:
                return await _publish_and_wait_zmq(
                    workflow_path=workflow_path,
                    workflow_graph=graph if workflow_path is None else None,
                    initial_inputs=initial_inputs,
                    unit_param_overrides=unit_param_overrides
                    if isinstance(unit_param_overrides, dict)
                    else None,
                    stream_cb=stream_cb if callable(stream_cb) else None,
                    format=fmt,
                    execution_timeout_s=execution_timeout_s,
                    zmq=zmq_cfg,
                )

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(_go(), loop)
                outputs = fut.result()
            else:
                outputs = asyncio.run(_go())
        else:
            outputs = run_workflow_inline(
                workflow_path=workflow_path,
                workflow_graph=cast(dict[str, Any] | None, graph)
                if workflow_path is None
                else None,
                initial_inputs=initial_inputs,
                unit_param_overrides=unit_param_overrides,
                format=fmt,
                execution_timeout_s=execution_timeout_s,
                stream_callback=(
                    (lambda token: (stream_cb(token), None)[1])
                    if callable(stream_cb)
                    else None
                ),
                run_id=None,
                zmq_publisher=None,
                send_job_message=False,
            )

        return ({"data": outputs, "error": ""}, state)
    except Exception as e:
        return ({"data": {}, "error": f"run_workflow execute failed: {e}"}, state)


def register_run_workflow() -> None:
    register_unit(
        UnitSpec(
            type_name="RunWorkflow",
            input_ports=RUN_WORKFLOW_INPUT_PORTS,
            output_ports=RUN_WORKFLOW_OUTPUT_PORTS,
            step_fn=_run_workflow_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description=(
                "Wrapper that preserves RunWorkflow payload semantics. "
                "If payload.path is set, loads the workflow from file; otherwise uses "
                "the graph input (current graph). If unit params.zmq is set, publishes "
                "job to workflow server and awaits results via ZMQ."
            ),
        )
    )


__all__ = [
    "register_run_workflow",
    "RUN_WORKFLOW_INPUT_PORTS",
    "RUN_WORKFLOW_OUTPUT_PORTS",
]
