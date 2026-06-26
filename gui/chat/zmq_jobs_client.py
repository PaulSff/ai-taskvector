from __future__ import annotations

import json
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional

import zmq
import zmq.asyncio

from runtime.zmq_messaging import ZmqPublisher, ZmqTopics

logger = logging.getLogger(__name__)

OnToken = Callable[
    [str, str], Awaitable[None]
]  # (session_id, token_piece) -> awaitable


async def publish_job_and_wait(
    *,
    job_pub_endpoint: str,
    job_topic: str,  # ignored
    response_endpoint: str,
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
    ctx = zmq.asyncio.Context.instance()

    sub = ctx.socket(zmq.SUB)
    sub.connect(response_endpoint)
    sub.setsockopt(zmq.SUBSCRIBE, b"")

    pub = ZmqPublisher(pub_endpoint=job_pub_endpoint, topics=topics)

    payload = {
        "run_id": run_id,
        "workflow_path": workflow_path,
        "initial_inputs": initial_inputs,
        "unit_param_overrides": unit_param_overrides,
        "format": format,
        "response_endpoint": response_endpoint,
        "update_endpoint": None,
        "execution_timeout_s": execution_timeout_s,
        "ts": time.time(),
    }

    logger.info(
        "publish_job_and_wait: publishing job topic=%r endpoint=%r run_id=%r wf=%r response_endpoint=%r",
        topics.job,
        job_pub_endpoint,
        run_id,
        workflow_path,
        response_endpoint,
    )

    pub.sock.send_multipart(
        [
            topics.job.encode("utf-8"),
            json.dumps(payload, default=str).encode("utf-8"),
        ]
    )

    logger.debug("publish_job_and_wait: sent payload keys=%s", list(payload.keys()))

    final_outputs: Optional[Dict[str, Any]] = None
    final_error: Optional[str] = None

    while True:
        frames = await sub.recv_multipart()
        if len(frames) < 2:
            continue

        topic = frames[0].decode("utf-8", "ignore")
        data = json.loads(frames[1].decode("utf-8"))

        if data.get("run_id") != run_id:
            continue
        if is_stale is not None and is_stale():
            logger.info("publish_job_and_wait: stale run_id=%r (stopping wait)", run_id)
            break

        logger.debug(
            "publish_job_and_wait: rx topic=%r keys=%s", topic, list(data.keys())
        )

        if topic == topics.token:
            token_piece = data.get("token") or ""
            if token_piece and token_callback is not None:
                await token_callback(session_id, token_piece)

        elif topic == topics.result:
            # never break; keep receiving
            final_outputs = data.get("outputs") or final_outputs or {}
            continue

        elif topic == topics.error:
            final_error = str(data.get("error") or "")
            logger.error(
                "publish_job_and_wait: got error run_id=%r error=%r",
                run_id,
                final_error,
            )
            break

    if final_error is not None:
        return {"error": final_error}

    return {"orchestrator": (final_outputs or {})}
