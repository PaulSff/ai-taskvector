from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from gui.chat.context.llm_prompt_inspector import attach_llm_prompt_debug_from_outputs
from gui.chat.utils import collect_workflow_errors
from runtime import ZmqPublisher, ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics
from runtime.run import WorkflowTimeoutError

from .paths import DEFAULT_EXECUTION_TIMEOUT_S, agent_WORKFLOW_PATH

# ---- fixed endpoint pools (configure N >= max concurrent calls) ----
N = 10

JOB_PUB_ENDPOINTS = [f"tcp://127.0.0.1:{6121 + 2 * i}" for i in range(N)]
RESPONSE_ENDPOINTS = [f"tcp://127.0.0.1:{6131 + 2 * i}" for i in range(N)]
RESPONSE_SUB_ENDPOINTS = RESPONSE_ENDPOINTS


def _missing_workflow_msg(path: Path) -> str:
    return f"Required workflow file not found: {path}"


FormatProcess = str  # keep if you want "dict" / etc later

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


async def _publish_and_wait(
    wp: Path,
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None,
    *,
    execution_timeout_s: float | None,
    stream_callback: Callable[[str], None] | None,
    format: FormatProcess = "dict",
) -> dict[str, Any]:
    slot = await _acquire_slot()
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

        job_pub = ZmqPublisher(pub_endpoint=JOB_PUB_ENDPOINTS[slot], topics=ZmqTopics())
        start = time.monotonic()

        await asyncio.wait_for(sub.start(), timeout=30)

        job_pub.publish_job(
            run_id=run_id,
            workflow_path=str(wp),
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
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
        await _release_slot()


async def run_agent_workflow(
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    execution_timeout_s: float | None = DEFAULT_EXECUTION_TIMEOUT_S,
    stream_callback: Callable[[str], None] | None = None,
    *,
    workflow_path: str | Path | None = None,
) -> dict[str, Any]:
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
