"""
- Normal workflow example:

The function waits for the first result, invokes ``on_result``, and returns
the same result to the caller.

```python
async def handle_normal_result(
    outputs: dict[str, object],
) -> None:
    logger.info("Normal workflow outputs: %s", outputs)

    # Update the console UI here.
    update_console(outputs)


normal_outputs = await run_via_jobs_and_await(
    workflow_graph=workflow_graph,
    initial_inputs=initial_inputs,
    unit_param_overrides=unit_param_overrides,
    format="dict",
    keep_alive=False,
    timeout_s=60.0,
    on_result=handle_normal_result,
)

logger.info("Normal workflow completed: %s", normal_outputs)
```

- Keep-alive workflow example:

The function invokes ``on_result`` for every result and remains subscribed
until its task is cancelled. It does not return after the first result.

```python
async def handle_keep_alive_result(
    outputs: dict[str, object],
) -> None:
    logger.info("Keep-alive update: %s", outputs)

    # Process or display every update received from the workflow.
    update_console(outputs)


keep_alive_task = asyncio.create_task(
    run_via_jobs_and_await(
        workflow_graph=workflow_graph,
        initial_inputs=initial_inputs,
        unit_param_overrides=unit_param_overrides,
        format="dict",
        keep_alive=True,
        timeout_s=None,
        on_result=handle_keep_alive_result,
    )
)

try:
    # The task continues receiving results indefinitely.
    await keep_alive_task

except asyncio.CancelledError:
    logger.info("Keep-alive workflow stopped")

finally:
    if not keep_alive_task.done():
        keep_alive_task.cancel()

        try:
            await keep_alive_task
        except asyncio.CancelledError:
            pass
```

For a keep-alive workflow, explicitly stop it by cancelling the task returned
by asyncio.create_task(). The cancellation handler publishes stop_workflow
using the existing job_pub, then waits for the update_batch response
with workflow_status == "stopped".

A synchronous example:

```python
def handle_result_sync(
    outputs: dict[str, object],
) -> None:
    logger.info("Received outputs: %s", outputs)


normal_outputs = await run_via_jobs_and_await(
    workflow_graph=workflow_graph,
    initial_inputs=initial_inputs,
    unit_param_overrides=unit_param_overrides,
    keep_alive=False,
    timeout_s=60.0,
    on_result=handle_result_sync,
)
```
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Literal, TypeGuard, cast

from core.schemas.process_graph import ProcessGraph
from gui.components.settings import (
    DEFAULT_CONSOLE_WORKFLOWS_CONCURRENT_CALLS,
    DEFAULT_RUN_CONSOLE_JOB_PUB_ENDPOINT,
    DEFAULT_RUN_CONSOLE_RESULT_SUB_ENDPOINT,
)
from runtime.run import WorkflowTimeoutError
from services.logging import setup_colored_logging
from services.server import (
    RoundRobinSlotAllocator,
    _parse_host_port,
)
from services.zmq import (
    ZmqPublisher,
    ZmqSubscriber,
    ZmqSubscriptionConfig,
    ZmqTopics,
)

JOB_PUB_ENDPOINT = DEFAULT_RUN_CONSOLE_JOB_PUB_ENDPOINT
RESULT_SUB_ENDPOINT = DEFAULT_RUN_CONSOLE_RESULT_SUB_ENDPOINT
RESPONSE_PUB_ENDPOINT = RESULT_SUB_ENDPOINT

N = DEFAULT_CONSOLE_WORKFLOWS_CONCURRENT_CALLS

workflow_host, workflow_port = _parse_host_port(JOB_PUB_ENDPOINT)
resp_host, resp_port = _parse_host_port(RESULT_SUB_ENDPOINT)

JOB_PUB_ENDPOINTS = [
    f"{workflow_host}:{workflow_port + 2 * i}"
    for i in range(N)
]

RESPONSE_ENDPOINTS = [
    f"{resp_host}:{resp_port + 2 * i}"
    for i in range(N)
]

RESPONSE_SUB_ENDPOINTS = RESPONSE_ENDPOINTS

_slot_allocator = RoundRobinSlotAllocator(N)

FormatProcess = Literal["dict", "yaml", "pyflow"]

logger = setup_colored_logging(logging.INFO)


# --- Callbacks ---

# Used for both update_batch and result
ResultCallback = Callable[
    [dict[str, object]],
    Awaitable[None] | None,
]

TokenCallback = Callable[
    [str],
    Awaitable[None] | None,
]

ErrorCallback = Callable[
    [str],
    Awaitable[None] | None,
]

# --------

def extract_keep_alive(graph: Mapping[str, object]) -> bool:
    return bool(graph.get("keep_alive", False))


def debug_log_param_overrides_for_graph_dict(
    graph: ProcessGraph,
    log_path: str,
) -> dict[str, dict[str, object]]:
    """Build Debug unit parameter overrides for the specified log path."""
    log_path = (log_path or "").strip()

    if not log_path:
        return {}

    overrides: dict[str, dict[str, object]] = {}

    for unit in graph.units:
        if (unit.type or "").strip() != "Debug":
            continue

        overrides[unit.id] = {
            "log_path": log_path,
        }

    return overrides


def is_str_object_dict(
    value: object,
) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False

    dictionary = cast(dict[object, object], value)
    return all(isinstance(key, str) for key in dictionary)


def _safe_repr_500(value: object) -> str:
    return repr(value)[:500]


def format_run_outputs(outputs: Mapping[str, object]) -> str:
    lines: list[str] = []

    for unit_id, port_values in sorted(outputs.items()):
        if not is_str_object_dict(port_values):
            lines.append(f"[{unit_id}] (non-dict output)")
            continue

        for port_name, value in sorted(port_values.items()):
            if value is None:
                formatted = "None"

            elif isinstance(value, str):
                formatted = value[:500]
                if len(value) > 500:
                    formatted += "..."

            elif isinstance(value, (dict, list)):
                try:
                    dumped = json.dumps(
                        value,
                        ensure_ascii=False,
                    )
                    formatted = dumped[:500]
                    if len(dumped) > 500:
                        formatted += "..."
                except (TypeError, ValueError):
                    formatted = _safe_repr_500(value)

            else:
                formatted = str(value)[:500]

            lines.append(
                f"  {unit_id}.{port_name}: {formatted}"
            )

    return "\n".join(lines) if lines else "(no outputs)"


def build_initial_inputs_for_run(
    graph: ProcessGraph,
    user_message: str,
) -> dict[str, dict[str, object]]:
    """
    Build initial inputs for Inject units.

    Each Inject receives ``{"data": user_message}`` when the message is
    non-empty. Empty messages are omitted so Inject units can use their
    configured parameters or template connections.
    """
    message = (user_message or "").strip()

    if not message:
        return {}

    return {
        unit.id: {"data": message}
        for unit in graph.units
        if unit.type == "Inject"
    }


async def _invoke_callback(
    callback: Callable[..., Awaitable[None] | None] | None,
    *args: object,
) -> None:
    if callback is None:
        return

    result = callback(*args)

    if result is not None:
        await result

class WorkflowRun:
    """Handle for a running workflow."""

    def __init__(
        self,
        *,
        workflow_graph: ProcessGraph,
        initial_inputs: dict[str, object] | None,
        unit_param_overrides: dict[str, dict[str, object]] | None,
        format: str = "dict",
        keep_alive: bool,
        timeout_s: float | None,
        on_result: ResultCallback | None = None,
        on_error: ErrorCallback | None = None,
        on_token: TokenCallback | None = None,
    ) -> None:
        self._stop_event = asyncio.Event()

        self.task = asyncio.create_task(
            run_via_jobs_and_await(
                workflow_graph=workflow_graph,
                initial_inputs=initial_inputs,
                unit_param_overrides=unit_param_overrides,
                format=format,
                keep_alive=keep_alive,
                timeout_s=timeout_s,
                on_result=on_result,
                on_error=on_error,
                on_token=on_token,
                stop_event=self._stop_event,
            )
        )

    async def stop(self, timeout_s: float = 30.0) -> None:
        """Explicitly request the remote workflow to stop."""
        self._stop_event.set()

        try:
            _ = await asyncio.wait_for(
                asyncio.shield(self.task),
                timeout=timeout_s,
            )
        except TimeoutError as exc:
            raise WorkflowTimeoutError(timeout_s) from exc

    async def wait(self) -> dict[str, object]:
        return await self.task


async def run_via_jobs_and_await(
    *,
    workflow_graph: ProcessGraph,
    initial_inputs: dict[str, object] | None,
    unit_param_overrides: dict[str, dict[str, object]] | None,
    format: str = "dict",
    keep_alive: bool,
    timeout_s: float | None,
    on_result: ResultCallback | None = None,
    on_error: ErrorCallback | None = None,
    on_token: TokenCallback | None = None,
    stop_event: asyncio.Event | None = None,
) -> dict[str, object]:

    """
    Publish a workflow job and receive its results.

    Normal mode:

    - Waits for the first result or workflow error.
    - Invokes ``on_result`` once.
    - Returns the result.
    - Applies ``timeout_s`` as the overall wait timeout.

    Keep-alive mode:

    - Invokes ``on_result`` for every received result.
    - Does not return after the first result.
    - Continues listening until cancelled or until a workflow error occurs.
    - Does not apply ``timeout_s`` as a subscriber wait timeout.

    The caller should cancel the returned task to stop a keep-alive run.
    """
    slot = await _slot_allocator.acquire()

    # This must be initialized before the try block because finally can run
    # even if an exception occurs before the body of try is entered fully.
    run_id = uuid.uuid4().hex

    sub: ZmqSubscriber | None = None
    job_pub: ZmqPublisher | None = None
    workflow_stopped = asyncio.Event()

    try:
        topics = ZmqTopics()

        logger.info(
            "Running workflow from Console (run_id=%s, keep_alive=%s)",
            run_id,
            keep_alive,
        )

        completed = asyncio.Event()
        workflow_error = ""

        final_outputs: dict[str, object] | None = None

        async def _on_error(
            _topic: str,
            payload: dict[str, object],
        ) -> None:
            nonlocal workflow_error

            if payload.get("run_id") != run_id:
                return

            error_value = payload.get("error")
            workflow_error = (
                error_value
                if isinstance(error_value, str)
                else str(error_value)
            )

            logger.error(
                "Console: Received workflow error (run_id=%s, error=%s)",
                run_id,
                workflow_error,
            )

            completed.set()

            await _invoke_callback(
                on_error,
                workflow_error,
            )

        async def _on_result(
            _topic: str,
            payload: dict[str, object],
        ) -> None:
            nonlocal final_outputs

            if payload.get("run_id") != run_id:
                return

            raw_outputs = payload.get("outputs")

            if is_str_object_dict(raw_outputs):
                outputs = dict(raw_outputs)
            else:
                outputs = {}

            logger.info(
                "Console: Received workflow result (run_id=%s, keys=%s, keep_alive=%s)",
                run_id,
                list(outputs.keys()),
                keep_alive,
            )

            # Both normal and keep-alive calls use the same result callback.
            await _invoke_callback(
                on_result,
                outputs,
            )

            if not keep_alive:
                final_outputs = outputs
                completed.set()


        async def _on_update_batch(
            _topic: str,
            payload: dict[str, object],
        ) -> None:
            if payload.get("run_id") != run_id:
                return

            if payload.get("workflow_status") == "stopped":
                logger.info(
                    "Console: Workflow stopped (run_id=%s)",
                    run_id,
                )

                workflow_stopped.set()
                completed.set()

                await _invoke_callback(
                    on_result,
                    {
                        "workflow_status": "stopped",
                        "update": True,
                        "ts": payload.get("ts"),
                    },
                )

                return

            raw_payload = payload.get("outputs")

            if is_str_object_dict(raw_payload):
                outputs = dict(raw_payload)
            else:
                outputs = {
                    "update": raw_payload,
                }

            logger.info(
                "Console: Received update_batch (run_id=%s, keys=%s)",
                run_id,
                list(outputs.keys()),
            )

            await _invoke_callback(
                on_result,
                outputs,
            )

        async def _on_token(
            _topic: str,
            payload: dict[str, object],
        ) -> None:
            if payload.get("run_id") != run_id:
                return

            token_value = payload.get("token")

            if not isinstance(token_value, str):
                return

            await _invoke_callback(
                on_token,
                token_value,
            )

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

        sub.on(topics.error, _on_error)
        sub.on(topics.result, _on_result)
        sub.on(topics.update_batch, _on_update_batch)
        sub.on(topics.token, _on_token)

        job_pub = ZmqPublisher(
            pub_endpoint=JOB_PUB_ENDPOINTS[slot],
            topics=topics,
        )

        await asyncio.wait_for(
            sub.start(),
            timeout=30,
        )

        logger.info(
            "Console: Subscriber started (run_id=%s, slot=%s)",
            run_id,
            slot,
        )

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

        if keep_alive:
            logger.info(
                "Console: Keep-alive subscriber listening (run_id=%s)",
                run_id,
            )

            if stop_event is None:
                _= await completed.wait()
            else:
                completed_task = asyncio.create_task(completed.wait())
                stop_task = asyncio.create_task(stop_event.wait())

                try:
                    done, _ = await asyncio.wait(
                        (completed_task, stop_task),
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    if stop_event.is_set():
                        assert job_pub is not None

                        stop_payload = {
                            "action": "stop_workflow",
                            "run_id": run_id,
                        }

                        stop_endpoint = JOB_PUB_ENDPOINTS[slot]
                        stop_topic = topics.action

                        job_pub.publish_action(
                            action=stop_payload["action"],
                            run_id=stop_payload["run_id"],
                        )

                        logger.info(
                            "Console: ZMQ stop_workflow message published successfully (topic=%s, endpoint=%s, payload=%r)",
                            stop_topic,
                            stop_endpoint,
                            stop_payload,
                        )

                        try:
                            _ = await asyncio.wait_for(
                                asyncio.shield(workflow_stopped.wait()),
                                timeout=30.0,
                            )
                        except TimeoutError:
                            logger.warning(
                                "Console: Timed out waiting for workflow stopped confirmation (run_id=%s)",
                                run_id,
                            )

                        completed.set()
                    elif completed_task in done:
                        await completed_task

                finally:
                    for task in (completed_task, stop_task):
                        if not task.done():
                            _ = task.cancel()

                    _ = await asyncio.gather(
                        completed_task,
                        stop_task,
                        return_exceptions=True,
                    )


        else:
            logger.info(
                "Console: Waiting for first result (run_id=%s, timeout_s=%s)",
                run_id,
                timeout_s,
            )

            if timeout_s is None:
                _ = await completed.wait()
            else:
                wait_timeout: float = timeout_s

                try:
                    _ = await asyncio.wait_for(
                        completed.wait(),
                        timeout=wait_timeout,
                    )
                except TimeoutError as exc:
                    logger.warning(
                        "Console: Overall wait timeout reached (run_id=%s, timeout_s=%s)",
                        run_id,
                        wait_timeout,
                    )
                    raise WorkflowTimeoutError(wait_timeout) from exc

        if workflow_error:
            raise RuntimeError(workflow_error)

        # Keep-alive mode normally does not reach this point. It exits only
        # after cancellation or a workflow error.
        return final_outputs or {}

    except asyncio.CancelledError:
        logger.info(
            "Console: Subscriber task cancelled (run_id=%s)",
            run_id,
        )
        raise

    finally:
        if sub is not None:
            try:
                logger.info(
                    "Console: Stopping subscriber (run_id=%s)",
                    run_id,
                )
                await sub.stop()
            except (RuntimeError, ValueError, TypeError):
                logger.exception(
                    "Console: Failed to stop subscriber (run_id=%s)",
                    run_id,
                )

        await _slot_allocator.release()
