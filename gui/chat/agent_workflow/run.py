"""Run a role chat workflow file and normalize ``merge_response.data`` for the GUI."""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from gui.chat.context.llm_prompt_inspector import attach_llm_prompt_debug_from_outputs
from gui.chat.utils import collect_workflow_errors
from runtime import ZmqPublisher, ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics
from runtime.run import WorkflowTimeoutError

from .paths import DEFAULT_EXECUTION_TIMEOUT_S, agent_WORKFLOW_PATH

JOB_PUB_ENDPOINT = "tcp://127.0.0.1:6665"
RESULT_SUB_ENDPOINT = "tcp://127.0.0.1:6675"
RESPONSE_PUB_ENDPOINT = RESULT_SUB_ENDPOINT  # as you stated


def run_agent_workflow(
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    execution_timeout_s: float | None = DEFAULT_EXECUTION_TIMEOUT_S,
    stream_callback: Callable[[str], None] | None = None,
    *,
    workflow_path: str | Path | None = None,
) -> dict[str, Any]:
    out_box: dict[str, Any] = {}
    err_box: dict[str, BaseException] = {}

    def _thread_target() -> None:
        async def _inner() -> None:
            try:
                out_box["result"] = await _run_agent_workflow_async(
                    initial_inputs=initial_inputs,
                    unit_param_overrides=unit_param_overrides,
                    execution_timeout_s=execution_timeout_s,
                    stream_callback=stream_callback,
                    workflow_path=workflow_path,
                )
            except BaseException as e:
                err_box["error"] = e

        asyncio.run(_inner())

    t = threading.Thread(target=_thread_target, daemon=True)
    t.start()
    t.join(timeout=execution_timeout_s if execution_timeout_s is not None else None)

    if "error" in err_box:
        raise err_box["error"]
    if "result" not in out_box:
        if execution_timeout_s is None:
            raise WorkflowTimeoutError(
                0.0, "Workflow execution did not return a result"
            )
        raise WorkflowTimeoutError(execution_timeout_s)

    return out_box["result"]


async def _run_agent_workflow_async(
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    execution_timeout_s: float | None = DEFAULT_EXECUTION_TIMEOUT_S,
    stream_callback: Callable[[str], None] | None = None,
    *,
    workflow_path: str | Path | None = None,
) -> dict[str, Any]:
    try:
        from units.data_bi import register_data_bi_units

        register_data_bi_units()
    except Exception:
        pass

    wp = (
        Path(workflow_path).resolve()
        if workflow_path is not None
        else agent_WORKFLOW_PATH
    )
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

    job_pub.publish_job(
        run_id=run_id,
        workflow_path=str(wp),
        initial_inputs=initial_inputs,
        unit_param_overrides=unit_param_overrides,
        format="dict",
        response_endpoint=RESPONSE_PUB_ENDPOINT,
    )

    start = time.monotonic()
    await sub.start()
    try:
        while final_outputs is None and not has_workflow_error:
            timeout_s = execution_timeout_s
            if timeout_s is not None and (time.monotonic() - start) > timeout_s:
                raise WorkflowTimeoutError(timeout_s)
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


# Note: workflow_designer_workflow.json wires merge_errors → debug_errors only; the GUI does not read
# merge_errors. Per-unit error ports (e.g. process) are collected via collect_workflow_errors(outputs).
