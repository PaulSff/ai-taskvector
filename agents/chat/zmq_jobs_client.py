from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable, Iterator
from copy import deepcopy
from dataclasses import dataclass
from typing import cast

from core.schemas import ProcessGraph
from core.schemas.primitives import (
    Data,
    JsonObject,
    JsonValue,
    WorkflowInputs,
    require_json_object_from_object,
)
from gui.components.settings import (
    get_turn_driver_job_pub_endpoint,
    get_turn_driver_max_concurrent_calls,
    get_turn_driver_response_endpoint,
    get_turn_driver_update_endpoint,
)
from services.server import (
    RoundRobinSlotAllocator,
    _parse_host_port,
)
from services.zmq import ZmqPublisher, ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics

logger = logging.getLogger(__name__)

OnToken = Callable[
    [str, str], Awaitable[None]
]  # (session_id, token_piece) -> awaitable


@dataclass
class JobState:
    final_error: str | None = None
    final_outputs: Data | None = None


# ---- fixed endpoint pools (configure N >= max concurrent calls) ----
WORKFLOW_SERVER_ENDPOINT = get_turn_driver_job_pub_endpoint()  # e.g. tcp://127.0.0.1:6679
TURN_DRIVER_RESPONSE_ENDPOINT = get_turn_driver_response_endpoint()  # e.g. tcp://127.0.0.1:xxxx
TURN_DRIVER_UPDATE_ENDPOINT = get_turn_driver_update_endpoint()

N = get_turn_driver_max_concurrent_calls()

workflow_host, workflow_port = _parse_host_port(WORKFLOW_SERVER_ENDPOINT)
resp_host, resp_port = _parse_host_port(TURN_DRIVER_RESPONSE_ENDPOINT)
upd_host, upd_port = _parse_host_port(TURN_DRIVER_UPDATE_ENDPOINT)

# ---- fixed endpoint pools (configure N >= max concurrent calls) ----
JOB_PUB_ENDPOINTS = [f"{workflow_host}:{workflow_port + 2 * i}" for i in range(N)]
RESPONSE_ENDPOINTS = [f"{resp_host}:{resp_port + 2 * i}" for i in range(N)]
RESPONSE_SUB_ENDPOINTS = RESPONSE_ENDPOINTS

# range for update-batch publisher endpoints to subscribe to
UPDATE_BATCH_ENDPOINTS = [f"{upd_host}:{upd_port + 2 * i}" for i in range(N)]

# Roundrobin slot allocator
_slot_allocator = RoundRobinSlotAllocator(N)

def _set_update_pub_endpoint_in_overrides(
    unit_param_overrides: WorkflowInputs | None,
    *,
    update_pub_endpoint: str,
    run_id: str,
) -> WorkflowInputs | None:
    if unit_param_overrides is None:
        return {
            "orchestrator": {
                "update_pub_endpoint": update_pub_endpoint,
                "run_id": run_id,
            }
        }

    copied = dict(unit_param_overrides)

    orch = copied.get("orchestrator")
    orch_dict = orch if isinstance(orch, dict) else {}

    copied["orchestrator"] = {
        **orch_dict,
        "update_pub_endpoint": update_pub_endpoint,
        "run_id": run_id,
    }

    return copied


# ------- find non-serializable ------
def find_non_jsonable(
    value: object,
    path: str = "payload",
) -> Iterator[tuple[str, str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            # JSON object keys must be strings, unless they are converted by
            # json.dumps(). Treat non-string keys as invalid for this protocol.
            if not isinstance(key, str):
                yield (
                    f"{path}[{key!r}]",
                    type(key).__name__,
                    "JSON object keys must be strings",
                )
            yield from find_non_jsonable(child, f"{path}[{key!r}]")

    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from find_non_jsonable(child, f"{path}[{index}]")

    elif isinstance(value, (str, int, float, bool)) or value is None:
        return

    else:
        # This catches ProcessGraph and other custom objects.
        try:
            _ = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError, OverflowError):
            yield path, type(value).__name__, repr(value)[:300]


# ---- Serialize initial inputs ----
def _serialize_initial_inputs(
    initial_inputs: WorkflowInputs | None,
) -> WorkflowInputs| None:
    if initial_inputs is None:
        return None

    serialized = deepcopy(initial_inputs)

    inject_context = serialized.get("inject_context")
    if not isinstance(inject_context, dict):
        return serialized

    context_data = inject_context.get("data")
    if not isinstance(context_data, dict):
        return serialized

    graph = context_data.get("graph")
    if graph is None:
        return serialized

    if not isinstance(graph, ProcessGraph):
        raise TypeError(
            "initial_inputs['inject_context']['data']['graph'] must be ProcessGraph, got {type(graph).__name__}"
        )

    context_data["graph"] = graph.model_dump(
        mode="json",
        by_alias=True,
    )

    return serialized


# ------- Publish the orchestration workflow job to workflow-server -------

async def publish_job_and_wait(
    *,
    run_id: str,
    workflow_path: str,
    initial_inputs: WorkflowInputs | None,
    unit_param_overrides: WorkflowInputs| None,
    format: str | None,
    execution_timeout_s: float | None,
    token_callback: OnToken | None,
    session_id: str,
    is_stale: Callable[[], bool] | None = None,
    topics: ZmqTopics | None = None,
    in_progress: JsonObject | None = None,
    in_progress_callback: Callable[
        [JsonObject], Awaitable[None]
    ] | None = None
) -> Data:
    if topics is None:
        topics = ZmqTopics()
    slot = await _slot_allocator.acquire()

    sub: ZmqSubscriber | None = None
    update_sub: ZmqSubscriber | None = None
    try:
        response_sub_endpoint = RESPONSE_SUB_ENDPOINTS[slot]
        update_batch_endpoint = UPDATE_BATCH_ENDPOINTS[slot]

        # Inject update_pub_endpoint into overrides for this slot
        updated_unit_param_overrides = _set_update_pub_endpoint_in_overrides(
            unit_param_overrides,
            update_pub_endpoint=update_batch_endpoint,
            run_id=run_id,
        )

        pub = ZmqPublisher(pub_endpoint=JOB_PUB_ENDPOINTS[slot], topics=topics)

        sub = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=response_sub_endpoint,
                topics=(topics.token, topics.result, topics.error),
                accept_topics=None,
                rcvtimeo_ms=200,
            )
        )

        update_sub = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=update_batch_endpoint,
                topics=(topics.update_batch,),
                accept_topics=None,
                rcvtimeo_ms=200,
            )
        )

        state = JobState()
        last_update: JsonObject = in_progress if in_progress is not None else {}

        async def _on_token(_topic: str, payload: JsonObject) -> None:
            if payload.get("run_id") != run_id:
                return

            # Ensure token_piece is cast to a string immediately
            token_piece = str(payload.get("token") or "")

            logger.debug(
                "zmq_jobs_client: token received run_id=%r session_id=%r piece=%r",
                run_id,
                session_id,
                token_piece,
            )

            if token_piece and token_callback is not None:
                # Now token_piece is definitely a 'str', so this is allowed
                await token_callback(session_id, token_piece)


        async def _on_result(_topic: str, payload: JsonObject) -> None:
            if payload.get("run_id") != run_id:
                return

            outs = payload.get("outputs")

            if isinstance(outs, dict):
                state.final_outputs = cast(dict[str, object], outs)

                logger.info(
                    "zmq_jobs_client: result received run_id=%r outputs_keys=%r",
                    run_id,
                    list(state.final_outputs.keys()),
                )


        async def _on_error(_topic: str, payload: JsonObject) -> None:
            if payload.get("run_id") != run_id:
                return

            err = payload.get("error")
            state.final_error = err if isinstance(err, str) else str(err)

            logger.error(
                "zmq_jobs_client: error received run_id=%r error=%r",
                run_id,
                state.final_error,
            )


        async def _on_batch_update(_topic: str, payload: JsonObject) -> None:
            nonlocal last_update

            if payload.get("run_id") != run_id:
                return

            last_update = payload

            try:
                msg_wrap = payload.get("message")

                msg_type: JsonValue| None = None
                msg_keys: list[str] = []
                inner_keys: list[str] = []

                if isinstance(msg_wrap, dict):
                    msg_type = msg_wrap.get("type")
                    inner = msg_wrap.get("message")
                    msg_keys = list(msg_wrap.keys())

                    if isinstance(inner, dict):
                        inner_keys = list(inner.keys())

                logger.info(
                    "zmq_jobs_client: batch_update run_id=%r "
                    + "message.type=%r message.keys=%r inner.message.keys=%r",
                    run_id,
                    msg_type,
                    msg_keys,
                    inner_keys,
                )
            except (ValueError, TypeError):
                logger.info(
                    "zmq_jobs_client: batch_update run_id=%r "
                    + "(logger shape extraction failed)",
                    run_id,
                )

            if in_progress_callback is not None:
                try:
                    await in_progress_callback(payload)
                except asyncio.CancelledError:
                    raise
                except (ValueError, TypeError) as e:
                    logger.warning(
                        "in_progress_callback failed (run_id=%r): %r",
                        run_id,
                        e,
                    )

        assert sub is not None
        assert update_sub is not None

        sub.on(topics.token, _on_token)
        sub.on(topics.result, _on_result)
        sub.on(topics.error, _on_error)
        update_sub.on(topics.update_batch, _on_batch_update)

        await sub.start()
        await update_sub.start()

        logger.info(
            "zmq_jobs_client: job published run_id=%r workflow_path=%r slot=%d session_id=%r update_batch_endpoint=%r",
            run_id,
            workflow_path,
            slot,
            session_id,
            update_batch_endpoint,
        )

        try:
            serializable_initial_inputs = _serialize_initial_inputs(
                initial_inputs
            )

            json_initial_inputs = (
                None
                if serializable_initial_inputs is None
                else require_json_object_from_object(
                    serializable_initial_inputs,
                    field="initial_inputs",
                )
            )

            json_unit_param_overrides = (
                None
                if updated_unit_param_overrides is None
                else require_json_object_from_object(
                    updated_unit_param_overrides,
                    field="unit_param_overrides",
                )
            )


            job_payload: JsonObject = {
                "run_id": run_id,
                "workflow_path": workflow_path,
                "initial_inputs": json_initial_inputs,
                "unit_param_overrides": json_unit_param_overrides,
                "format": format,
                "response_endpoint": response_sub_endpoint,
                "update_endpoint": None,
                "execution_timeout_s": execution_timeout_s,
            }

            serialization_problems = list(find_non_jsonable(job_payload))

            if serialization_problems:
                for path, type_name, representation in serialization_problems:
                    logger.error(
                        "Non-JSON-serializable job payload value: "
                        + "path=%s type=%s value=%s",
                        path,
                        type_name,
                        representation,
                    )

                details = "; ".join(
                    f"{path}: {type_name}"
                    for path, type_name, _ in serialization_problems
                )

                raise TypeError(
                    f"Cannot publish job {run_id!r}; "
                    + f"payload contains non-JSON-serializable values: {details}"
                )

            pub.publish_job(
                run_id=run_id,
                workflow_path=workflow_path,
                initial_inputs=json_initial_inputs,
                unit_param_overrides=json_unit_param_overrides,
                format=format,
                response_endpoint=response_sub_endpoint,
                update_endpoint=None,
                execution_timeout_s=execution_timeout_s,
            )

            start = time.monotonic()
            while state.final_error is None and state.final_outputs is None:
                if is_stale is not None and is_stale():
                    logger.info(
                        "zmq_jobs_client: stale run_id=%r (stopping wait)", run_id
                    )
                    break

                if (
                    execution_timeout_s is not None
                    and (time.monotonic() - start) > execution_timeout_s
                ):
                    break

                await asyncio.sleep(0.01)


        finally:
            await update_sub.stop()
            await sub.stop()

        if state.final_error is not None:
            return {
                "orchestrator": {
                    "error": {
                        "error": state.final_error,
                    }
                }
            }

        if state.final_outputs is not None:
            return {
                "orchestrator": state.final_outputs,
            }

        return {"orchestrator": last_update}


    finally:
        # always release the slot
        await _slot_allocator.release()
