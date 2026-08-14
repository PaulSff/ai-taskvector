from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import cast

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
    unit_param_overrides: dict[str, object] | None,
    *,
    update_pub_endpoint: str,
    run_id: str,
) -> dict[str, object] | None:
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
    orch_dict = cast(dict[str, object], orch if isinstance(orch, dict) else {})
    copied["orchestrator"] = {
        **orch_dict,
        "update_pub_endpoint": update_pub_endpoint,
        "run_id": run_id,
    }
    return copied

# ------- Publish the orchestration workflow job to workflow-server -------

async def publish_job_and_wait(
    *,
    run_id: str,
    workflow_path: str,
    initial_inputs: dict[str, object] | None,
    unit_param_overrides: dict[str, object] | None,
    format: str | None,
    execution_timeout_s: float | None,
    token_callback: OnToken | None,
    session_id: str,
    is_stale: Callable[[], bool] | None = None,
    topics: ZmqTopics | None = None,
    in_progress: dict[str, object] | None = None,
    in_progress_callback: Callable[[dict[str, object]], Awaitable[None]] | None = None,
) -> dict[str, object]:
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

        final_outputs: dict[str, object] = {}
        had_final_outputs = False
        final_error: object = None
        last_update: dict[str, object] = in_progress or {}

        async def _on_token(_topic: str, payload: dict[str, object]) -> None:
            nonlocal final_error
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


        async def _on_result(_topic: str, payload: dict[str, object]) -> None:
            nonlocal had_final_outputs, final_outputs
            if payload.get("run_id") != run_id:
                return

            # 1. Get the value (type is object | None)
            outs = payload.get("outputs")

            # 2. Verify it's a dict
            if isinstance(outs, dict):
                # 3. Cast it to a known type to resolve "Unknown" and "dict[Unknown, Unknown]"
                final_outputs = cast(dict[str, object], outs)
                had_final_outputs = True

                logger.info(
                    "zmq_jobs_client: result received run_id=%r outputs_keys=%r",
                    run_id,
                    list(final_outputs.keys()), # inferred as list[str]
                )

        async def _on_error(_topic: str, payload: dict[str, object]) -> None:
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

        async def _on_batch_update(_topic: str, payload: dict[str, object]) -> None:
            nonlocal last_update
            if payload.get("run_id") != run_id:
                return
            last_update = payload

            try:
                msg_wrap = payload.get("message")

                # 1. Explicitly type your variables to avoid "Unknown" inference
                msg_type: object | None = None
                msg_keys: list[str] = []
                inner_keys: list[str] = []

                if isinstance(msg_wrap, dict):
                    # 2. Cast msg_wrap to a known dict type
                    msg_wrap = cast(dict[str, object], msg_wrap)

                    msg_type = msg_wrap.get("type")
                    inner = msg_wrap.get("message")

                    # .keys() is known to be str, so list() is list[str]
                    msg_keys = list(msg_wrap.keys())

                    if isinstance(inner, dict):
                        # 3. Cast inner to a known dict type
                        inner = cast(dict[str, object], inner)
                        inner_keys = list(inner.keys())

                logger.info(
                    "zmq_jobs_client: batch_update run_id=%r message.type=%r message.keys=%r inner.message.keys=%r",
                    run_id,
                    msg_type,
                    msg_keys,
                    inner_keys,
                )
            except (ValueError, TypeError):
                logger.info(
                    "zmq_jobs_client: batch_update run_id=%r (logger shape extraction failed)",
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
            pub.publish_job(
                run_id=run_id,
                workflow_path=workflow_path,
                initial_inputs=initial_inputs,
                unit_param_overrides=updated_unit_param_overrides,
                format=format,
                response_endpoint=response_sub_endpoint,
                update_endpoint=None,
                execution_timeout_s=execution_timeout_s,
            )

            start = time.monotonic()
            while final_error is None and not had_final_outputs:
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
            # Remove 'if is not None' because the type checker
            # knows these were successfully initialized.
            await update_sub.stop()
            await sub.stop()

        # This code will NO LONGER be "unreachable" once you
        # fix the while loop logic from the previous step.
        if final_error is not None:
            return {"orchestrator": {"error": {"error": final_error}}}

        if had_final_outputs:
            return {"orchestrator": final_outputs}

        return {"orchestrator": last_update}

    finally:
        # always release the slot
        await _slot_allocator.release()
