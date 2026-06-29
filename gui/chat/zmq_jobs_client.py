from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional

from runtime import ZmqPublisher, ZmqSubscriber, ZmqSubscriptionConfig, ZmqTopics

logger = logging.getLogger(__name__)

OnToken = Callable[
    [str, str], Awaitable[None]
]  # (session_id, token_piece) -> awaitable


# ---- fixed endpoint pools (configure N >= max concurrent calls) ----
N = 10

JOB_PUB_ENDPOINTS = [f"tcp://127.0.0.1:{6601 + 2 * i}" for i in range(N)]
RESPONSE_ENDPOINTS = [f"tcp://127.0.0.1:{6611 + 2 * i}" for i in range(N)]
RESPONSE_SUB_ENDPOINTS = RESPONSE_ENDPOINTS


# ---- internal slot allocator ----
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
) -> Dict[str, Any]:
    slot = await _acquire_slot()
    try:
        pub = ZmqPublisher(pub_endpoint=JOB_PUB_ENDPOINTS[slot], topics=topics)

        sub = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=RESPONSE_SUB_ENDPOINTS[slot],
                topics=(topics.token, topics.result, topics.error),
                accept_topics=None,
                rcvtimeo_ms=200,
            )
        )

        final_outputs: Optional[Dict[str, Any]] = None
        final_error: Any = None

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
            nonlocal final_outputs
            if payload.get("run_id") != run_id:
                return
            outs = payload.get("outputs") or {}
            if isinstance(outs, dict):
                final_outputs = outs
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

        sub.on(topics.token, _on_token)
        sub.on(topics.result, _on_result)
        sub.on(topics.error, _on_error)

        await sub.start()

        logger.info(
            "zmq_jobs_client: job published run_id=%r workflow_path=%r slot=%d session_id=%r",
            run_id,
            workflow_path,
            slot,
            session_id,
        )

        try:
            pub.publish_job(
                run_id=run_id,
                workflow_path=workflow_path,
                initial_inputs=initial_inputs,
                unit_param_overrides=unit_param_overrides,
                format=format,
                response_endpoint=RESPONSE_ENDPOINTS[slot],
                update_endpoint=None,
                execution_timeout_s=execution_timeout_s,
            )

            start = time.monotonic()
            while True:
                if final_error is not None:
                    break
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
            await sub.stop()

        if final_error is not None:
            return {"orchestrator": {"error": {"error": final_error}}}

        return {"orchestrator": (final_outputs or {})}

    finally:
        await _release_slot()
