"""Workflow Designer–specific chat workflow execution (dev: run current canvas graph in memory)."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable, Optional

from core.schemas.process_graph import ProcessGraph
from gui.chat.context.llm_prompt_inspector import attach_llm_prompt_debug_from_outputs
from gui.chat.utils import collect_workflow_errors
from gui.components.workflow_tab.workflows.core_workflows import run_normalize_graph
from runtime import ZmqPublisher, ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics
from runtime.run import WorkflowTimeoutError
from units.data_bi import register_data_bi_units  # keep same as your other runner

JOB_PUB_ENDPOINT = "tcp://127.0.0.1:6662"
RESULT_SUB_ENDPOINT = "tcp://127.0.0.1:6672"
RESPONSE_PUB_ENDPOINT = RESULT_SUB_ENDPOINT


async def run_current_graph(
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    execution_timeout_s: float | None = None,
    stream_callback: Callable[[str], None] | None = None,
    *,
    workflow_graph: ProcessGraph | dict[str, Any] | None = None,
) -> dict[str, Any]:
    # --- same unit registration as your other runner ---
    try:
        register_data_bi_units()
    except Exception:
        pass

    if workflow_graph is None:
        return {
            "reply": "",
            "result": {},
            "status": {},
            "graph": None,
            "diff": "",
            "parser_output": None,
            "run_output": {},
            "report_output": {},
            "grep_output": {},
            "formulas_calc_output": {},
            "formulas_calc_error": "",
            "delegate_request": {},
            "delegate_request_error": "",
            "workflow_errors": [("run_agent_workflow_from_graph", "No graph loaded.")],
        }

    # --- normalize in-memory graph into a dict payload the worker can consume ---
    if isinstance(workflow_graph, ProcessGraph):
        pg = workflow_graph
        g_dict = pg.model_dump(by_alias=True)
    else:
        g_dict = (
            workflow_graph
            if isinstance(workflow_graph, dict)
            else (
                workflow_graph.model_dump(by_alias=True)
                if hasattr(workflow_graph, "model_dump")
                else None
            )
        )
        if g_dict is None:
            return {
                "reply": "",
                "result": {},
                "status": {},
                "graph": None,
                "diff": "",
                "parser_output": None,
                "run_output": {},
                "report_output": {},
                "grep_output": {},
                "formulas_calc_output": {},
                "formulas_calc_error": "",
                "delegate_request": {},
                "delegate_request_error": "",
                "workflow_errors": [
                    (
                        "run_agent_workflow_from_graph",
                        "Graph must be dict or ProcessGraph.",
                    )
                ],
            }

    g_norm, norm_err = run_normalize_graph(g_dict, format="dict")
    if norm_err or g_norm is None:
        return {
            "reply": "",
            "result": {},
            "status": {},
            "graph": None,
            "diff": "",
            "parser_output": None,
            "run_output": {},
            "report_output": {},
            "grep_output": {},
            "formulas_calc_output": {},
            "formulas_calc_error": "",
            "delegate_request": {},
            "delegate_request_error": "",
            "workflow_errors": [
                ("run_agent_workflow_from_graph", norm_err or "Normalize failed")
            ],
        }

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
        if isinstance(outs, dict):
            final_outputs = outs

    async def _on_token(_topic: str, payload: dict[str, Any]) -> None:
        if payload.get("run_id") != run_id:
            return
        tok = payload.get("token")
        if isinstance(tok, str) and stream_callback is not None:
            stream_callback(tok)

    sub.on(topics.token, _on_token)
    sub.on(topics.result, _on_result)
    sub.on(topics.error, _on_error)

    # IMPORTANT: send workflow_graph instead of workflow_path
    job_pub.publish_job(
        run_id=run_id,
        workflow_path=None,  # if worker requires the field, keep it but unused
        workflow_graph=g_norm,  # <-- the key change
        initial_inputs=initial_inputs,
        unit_param_overrides=unit_param_overrides,
        format="dict",
        response_endpoint=RESPONSE_PUB_ENDPOINT,
    )

    start = time.monotonic()
    await sub.start()
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

    # --- keep your existing shaping logic exactly as in your current run_agent_workflow ---
    data = (outputs.get("merge_response") or {}).get("data")
    if not isinstance(data, dict):
        data = {
            "reply": "",
            "result": {},
            "status": {},
            "graph": None,
            "diff": "",
            "parser_output": None,
            "run_output": {},
            "report_output": {},
            "grep_output": {},
            "formulas_calc_output": {},
            "formulas_calc_error": "",
            "delegate_request": {},
            "delegate_request_error": "",
        }
    if "parser_output" not in data:
        data = {**data, "parser_output": None}
    if "run_output" not in data:
        data = {**data, "run_output": {}}
    if "report_output" not in data:
        data = {**data, "report_output": {}}
    if "grep_output" not in data:
        data = {**data, "grep_output": {}}
    if "formulas_calc_output" not in data:
        data = {**data, "formulas_calc_output": {}}
    if "formulas_calc_error" not in data:
        data = {**data, "formulas_calc_error": ""}
    if "delegate_request" not in data:
        data = {**data, "delegate_request": {}}
    if "delegate_request_error" not in data:
        data = {**data, "delegate_request_error": ""}

    reply_val = data.get("reply")
    if not (isinstance(reply_val, str) and reply_val.strip()):
        llm_out = outputs.get("llm_agent") or {}
        if isinstance(llm_out.get("action"), str) and llm_out["action"].strip():
            data = {**data, "reply": llm_out["action"].strip()}

    data["workflow_errors"] = collect_workflow_errors(outputs)
    attach_llm_prompt_debug_from_outputs(outputs, data)
    return data
