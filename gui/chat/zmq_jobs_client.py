from __future__ import annotations

import asyncio
import re
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional

from runtime import ZmqPublisher, ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics
from gui.components.settings import (
    get_turn_driver_job_pub_endpoint,
    get_turn_driver_response_endpoint,
    get_turn_driver_update_endpoint,
    get_turn_driver_max_concurrent_calls,
)

logger = logging.getLogger(__name__)

OnToken = Callable[
    [str, str], Awaitable[None]
]  # (session_id, token_piece) -> awaitable


# ---- fixed endpoint pools (configure N >= max concurrent calls) ----
WORKFLOW_SERVER_ENDPOINT = get_turn_driver_job_pub_endpoint()  # e.g. tcp://127.0.0.1:6679
TURN_DRIVER_RESPONSE_ENDPOINT = get_turn_driver_response_endpoint()  # e.g. tcp://127.0.0.1:xxxx
TURN_DRIVER_UPDATE_ENDPOINT = get_turn_driver_update_endpoint()

N = get_turn_driver_max_concurrent_calls()

def _parse_host_port(endpoint: str) -> tuple[str, int]:
    # "tcp://127.0.0.1:6679" -> ("tcp://127.0.0.1", 6679)
    m = re.match(r"^(.*):(\d+)$", endpoint)
    if not m:
        raise ValueError(f"Unexpected endpoint format: {endpoint}")
    return m.group(1), int(m.group(2))

workflow_host, workflow_port = _parse_host_port(WORKFLOW_SERVER_ENDPOINT)
resp_host, resp_port = _parse_host_port(TURN_DRIVER_RESPONSE_ENDPOINT)
upd_host, upd_port = _parse_host_port(TURN_DRIVER_UPDATE_ENDPOINT)

# ---- fixed endpoint pools (configure N >= max concurrent calls) ----
JOB_PUB_ENDPOINTS = [f"{workflow_host}:{workflow_port + 2 * i}" for i in range(N)]
RESPONSE_ENDPOINTS = [f"{resp_host}:{resp_port + 2 * i}" for i in range(N)]
RESPONSE_SUB_ENDPOINTS = RESPONSE_ENDPOINTS

# range for update-batch publisher endpoints to subscribe to
UPDATE_BATCH_ENDPOINTS = [f"{upd_host}:{upd_port + 2 * i}" for i in range(N)]


# ---- internal slot allocator (shared across pub/sub pairs) ----
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


def _set_update_pub_endpoint_in_overrides(
    unit_param_overrides: Optional[Dict[str, Any]],
    *,
    update_pub_endpoint: str,
    run_id: str,
) -> Optional[Dict[str, Any]]:
    # Keep caller's dict immutable
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


async def publish_job_and_wait(
    *,
    run_id: str,
    workflow_path: str,
    initial_inputs: Optional[Dict[str, Any]],
    unit_param_overrides: Optional[Dict[str, Any]],
    format: Optional[str],
    execution_timeout_s: Optional[float],
    token_callback: Optional[OnToken],
    session_id: str,
    is_stale: Optional[Callable[[], bool]] = None,
    topics: ZmqTopics = ZmqTopics(),
    in_progress: Optional[Dict[str, Any]] = None,
    in_progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
) -> Dict[str, Any]:
    slot = await _acquire_slot()
    try:
        response_sub_endpoint = RESPONSE_SUB_ENDPOINTS[slot]
        update_batch_endpoint = UPDATE_BATCH_ENDPOINTS[slot]

        # Inject update_pub_endpoint into overrides for this slot
        updated_unit_param_overrides = _set_update_pub_endpoint_in_overrides(
            unit_param_overrides,
            update_pub_endpoint=update_batch_endpoint,
            run_id=run_id,  # orchestrator uses this run_id for its update_batch emitted outside of runtime
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

        final_outputs: Dict[str, Any] = {}
        had_final_outputs = False
        final_error: Any = None

        last_update: Dict[str, Any] = in_progress or {}

        async def _on_token(_topic: str, payload: Dict[str, Any]) -> None:
            nonlocal final_error
            if payload.get("run_id") != run_id:
                return
            token_piece = payload.get("token") or ""
            logger.debug(
                "zmq_jobs_client: token received run_id=%r session_id=%r piece=%r",
                run_id,
                session_id,
                token_piece,
            )
            if token_piece and token_callback is not None:
                await token_callback(session_id, token_piece)

        async def _on_result(_topic: str, payload: Dict[str, Any]) -> None:
            nonlocal had_final_outputs, final_outputs
            if payload.get("run_id") != run_id:
                return
            outs = payload.get("outputs") or {}
            if isinstance(outs, dict):
                final_outputs = outs
                had_final_outputs = True
                logger.info(
                    "zmq_jobs_client: result received run_id=%r outputs_keys=%r",
                    run_id,
                    list(final_outputs.keys()),
                )

        async def _on_error(_topic: str, payload: Dict[str, Any]) -> None:
            nonlocal final_error
            if payload.get("run_id") != run_id:
                return
            err = payload.get("error")
            final_error = err if isinstance(err, str) else str(err)
            logger.error(
                "zmq_jobs_client: error received run_id=%r error=%r",
                run_id,
                final_error,
            )

        async def _on_batch_update(_topic: str, payload: Dict[str, Any]) -> None:
            nonlocal last_update
            if payload.get("run_id") != run_id:
                return
            last_update = payload

            try:
                msg_wrap = payload.get("message")
                msg_type = None
                msg_keys = []
                inner_keys = []
                if isinstance(msg_wrap, dict):
                    msg_type = msg_wrap.get("type")
                    inner = msg_wrap.get("message")
                    msg_keys = list(msg_wrap.keys())
                    if isinstance(inner, dict):
                        inner_keys = list(inner.keys())

                logger.info(
                    "zmq_jobs_client: batch_update run_id=%r message.type=%r message.keys=%r inner.message.keys=%r",
                    run_id,
                    msg_type,
                    msg_keys,
                    inner_keys,
                )
            except Exception:
                logger.info(
                    "zmq_jobs_client: batch_update run_id=%r (logger shape extraction failed)",
                    run_id,
                )

            if in_progress_callback is not None:
                try:
                    await in_progress_callback(payload)
                except Exception:
                    pass

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
            pub.publish_job(
                run_id=run_id,
                workflow_path=workflow_path,
                initial_inputs=initial_inputs,
                unit_param_overrides=updated_unit_param_overrides,  # orchestrator update endpoint injected here
                format=format,
                response_endpoint=response_sub_endpoint,
                update_endpoint=None,
                execution_timeout_s=execution_timeout_s,
            )

            start = time.monotonic()
            while True:
                if final_error is not None:
                    break
                if had_final_outputs:
                    break  # we have to break the loop, otherwise the handle_turn is going to keep waiting forever
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

        if final_error is not None:
            return {"orchestrator": {"error": {"error": final_error}}}

        if had_final_outputs:
            return {"orchestrator": final_outputs}

        return {"orchestrator": last_update}

    finally:
        await _release_slot()
