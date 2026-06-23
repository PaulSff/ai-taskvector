# runtime/workflow_worker_pool.py
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from multiprocessing import get_context
from typing import Any, Dict, Optional

from runtime import (
    ZmqPublisher,
    ZmqSubscriber,
    ZmqSubscriptionConfig,
    ZmqTopics,
    run_workflow,
)

logger = logging.getLogger("workflow_worker_pool")

# ---- constants ----
DEFAULT_JOB_ENDPOINT = "tcp://127.0.0.1:6666"
DEFAULT_RCVTIMEO_MS = 1000
DEFAULT_MAX_CONCURRENCY = max(1, (os.cpu_count() or 4) - 1)
DEFAULT_EXECUTION_TIMEOUT_S_ENV = "WORKFLOW_EXECUTION_TIMEOUT_S"
DEFAULT_WORKER_MAX_CONCURRENCY_ENV = "WORKER_MAX_CONCURRENCY"
DEFAULT_SUB_TOPICS = (ZmqTopics().job,)


@dataclass(frozen=True)
class WorkerPoolConfig:
    job_endpoint: str = DEFAULT_JOB_ENDPOINT
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    sub_topics: tuple[str, ...] = DEFAULT_SUB_TOPICS
    rcvtimeo_ms: int = DEFAULT_RCVTIMEO_MS
    execution_timeout_s: Optional[float] = None


def _run_job_in_subprocess(
    *,
    run_id: str,
    workflow_path: str,
    initial_inputs: Optional[dict[str, Any]],
    unit_param_overrides: Optional[dict[str, Any]],
    format: Optional[str],
    response_endpoint: Optional[str],
    execution_timeout_s: Optional[float],
) -> dict[str, Any]:
    zmq_publisher = None
    if response_endpoint:
        zmq_publisher = ZmqPublisher(pub_endpoint=response_endpoint, topics=ZmqTopics())

    return run_workflow(
        workflow_path,
        initial_inputs=initial_inputs,
        unit_param_overrides=unit_param_overrides,
        execution_timeout_s=execution_timeout_s,
        run_id=run_id,
        zmq_publisher=zmq_publisher,
    )


def _proc_entrypoint(
    q: Any,
    *,
    run_id: str,
    workflow_path: str,
    initial_inputs: Optional[dict[str, Any]],
    unit_param_overrides: Optional[dict[str, Any]],
    format_hint: Optional[str],
    response_endpoint: Optional[str],
    execution_timeout_s: Optional[float],
) -> None:
    # IMPORTANT: top-level function => picklable under "spawn"
    try:
        out = _run_job_in_subprocess(
            run_id=run_id,
            workflow_path=workflow_path,
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format=format_hint,
            response_endpoint=response_endpoint,
            execution_timeout_s=execution_timeout_s,
        )
        q.put({"ok": True, "outputs": out})
    except BaseException as e:
        q.put({"ok": False, "error": str(e)})


async def run_worker_pool(cfg: WorkerPoolConfig) -> None:
    logger.info(
        "Worker pool started; subscribing to %s topics=%s",
        cfg.job_endpoint,
        cfg.sub_topics,
    )

    ctx = get_context("spawn")
    sem = asyncio.Semaphore(cfg.max_concurrency)

    sub = ZmqSubscriber(
        config=ZmqSubscriptionConfig(
            sub_endpoint=cfg.job_endpoint,
            topics=cfg.sub_topics,
            accept_topics=None,
            rcvtimeo_ms=cfg.rcvtimeo_ms,
        )
    )

    async def handle_job(topic: str, payload: Dict[str, Any]) -> None:
        async with sem:
            logger.info(
                "Job received topic=%s payload_keys=%s", topic, list(payload.keys())
            )

            run_id = payload.get("run_id")
            workflow_path = payload.get("workflow_path")
            initial_inputs = payload.get("initial_inputs")
            unit_param_overrides = payload.get("unit_param_overrides")
            format_hint = payload.get("format")
            response_endpoint = payload.get("response_endpoint")

            if not isinstance(run_id, str) or not isinstance(workflow_path, str):
                logger.error(
                    "Invalid job payload (missing run_id/workflow_path): %r", payload
                )
                return

            logger.info(
                "Starting job run_id=%s workflow=%s response_endpoint=%s",
                run_id,
                workflow_path,
                response_endpoint,
            )

            loop = asyncio.get_running_loop()
            result_fut: asyncio.Future[Dict[str, Any]] = loop.create_future()

            q = ctx.Queue()
            p = ctx.Process(
                target=_proc_entrypoint,
                kwargs=dict(
                    q=q,
                    run_id=run_id,
                    workflow_path=workflow_path,
                    initial_inputs=initial_inputs,
                    unit_param_overrides=unit_param_overrides,
                    format_hint=format_hint,
                    response_endpoint=response_endpoint,
                    execution_timeout_s=cfg.execution_timeout_s,
                ),
                daemon=True,
            )
            p.start()

            import threading

            def _wait_and_set() -> None:
                try:
                    msg = q.get()
                    if not isinstance(msg, dict):
                        msg = {
                            "ok": False,
                            "error": f"Unexpected worker response type: {type(msg).__name__}",
                        }
                    loop.call_soon_threadsafe(result_fut.set_result, msg)
                except BaseException as e:
                    loop.call_soon_threadsafe(
                        result_fut.set_result, {"ok": False, "error": str(e)}
                    )

            threading.Thread(target=_wait_and_set, daemon=True).start()

            try:
                msg = await result_fut
                if msg.get("ok"):
                    logger.info(
                        "Response published run_id=%s response_endpoint=%s",
                        run_id,
                        response_endpoint,
                    )
                else:
                    logger.error(
                        "Job failed run_id=%s response_endpoint=%s error=%s",
                        run_id,
                        response_endpoint,
                        msg.get("error"),
                    )
            finally:
                p.join(timeout=1)
                # If it’s still alive, don’t hang forever; terminate to avoid queue/process leaks.
                if p.is_alive():
                    p.terminate()
                    p.join(timeout=1)

    sub.on(ZmqTopics().job, handle_job)
    await sub.start()

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await sub.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    max_concurrency = (
        int(os.getenv(DEFAULT_WORKER_MAX_CONCURRENCY_ENV, "0"))
        or DEFAULT_MAX_CONCURRENCY
    )
    execution_timeout_s = float(os.getenv(DEFAULT_EXECUTION_TIMEOUT_S_ENV, "0")) or None

    cfg = WorkerPoolConfig(
        job_endpoint=DEFAULT_JOB_ENDPOINT,
        max_concurrency=max_concurrency,
        execution_timeout_s=execution_timeout_s,
    )
    asyncio.run(run_worker_pool(cfg))
