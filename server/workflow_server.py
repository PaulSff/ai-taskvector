from __future__ import annotations

import asyncio
import json
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

DEFAULT_RCVTIMEO_MS = 1000
DEFAULT_MAX_CONCURRENCY = max(1, (os.cpu_count() or 4) - 1)
DEFAULT_EXECUTION_TIMEOUT_S_ENV = "WORKFLOW_EXECUTION_TIMEOUT_S"
DEFAULT_WORKER_MAX_CONCURRENCY_ENV = "WORKER_MAX_CONCURRENCY"
DEFAULT_SUB_LIST_PATH = "zmq_subscription_list.json"

# Your handler expects job messages to arrive on ZmqTopics().job
DEFAULT_JOB_TOPIC = ZmqTopics().job


@dataclass(frozen=True)
class WorkerPoolConfig:
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    rcvtimeo_ms: int = DEFAULT_RCVTIMEO_MS
    execution_timeout_s: Optional[float] = None
    subscription_list_path: str = DEFAULT_SUB_LIST_PATH


def _load_subscriptions_from_json(path: str) -> list[tuple[str, tuple[str, ...]]]:
    """
    Input JSON:
    {
      "subscriptions": [
        { "name": "...", "sub_endpoint": "tcp://...", "topic_idx": "0" },
        ...
      ],
      "topics": ["job", "result", ...]
    }

    Returns list of (sub_endpoint, topics_tuple_for_that_subscriber).
    """
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    topics_arr = data.get("topics") or []
    subs = data.get("subscriptions") or []

    if not isinstance(topics_arr, list) or not isinstance(subs, list):
        return []

    out: list[tuple[str, tuple[str, ...]]] = []
    for item in subs:
        if not isinstance(item, dict):
            continue
        sub_endpoint = item.get("sub_endpoint")
        topic_idx = item.get("topic_idx")

        if not isinstance(sub_endpoint, str):
            continue

        # topic_idx may be string or int in your file; accept both
        idx: Optional[int] = None
        if isinstance(topic_idx, int):
            idx = topic_idx
        elif isinstance(topic_idx, str):
            try:
                idx = int(topic_idx)
            except ValueError:
                idx = None

        if idx is None or idx < 0 or idx >= len(topics_arr):
            continue

        topic_name = topics_arr[idx]
        if not isinstance(topic_name, str):
            continue

        out.append((sub_endpoint, (topic_name,)))

    return out


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
    subs = _load_subscriptions_from_json(cfg.subscription_list_path)

    # If JSON is empty/missing, you can fail fast or fallback. Here we fail fast.
    if not subs:
        raise RuntimeError(
            f"No valid subscriptions found in {cfg.subscription_list_path}"
        )

    # One subscriber per entry in JSON
    sub_instances: list[ZmqSubscriber] = []

    logger.info(
        "Worker pool started; subscribers=%s rcvtimeo_ms=%s",
        len(subs),
        cfg.rcvtimeo_ms,
    )
    for ep, topics in subs:
        logger.info("  subscribing endpoint=%s topics=%s", ep, topics)

    ctx = get_context("spawn")
    sem = asyncio.Semaphore(cfg.max_concurrency)

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
                if p.is_alive():
                    p.terminate()
                    p.join(timeout=1)

    # Create subscribers and register handler (only for job-topic messages)
    for ep, topics in subs:
        sub = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=ep,
                topics=topics,
                accept_topics=None,
                rcvtimeo_ms=cfg.rcvtimeo_ms,
            )
        )

        # Only attach handler for whatever topic string corresponds to "job"
        # If your JSON topics array contains "job", and ZmqTopics().job equals that,
        # this works. Otherwise set DEFAULT_JOB_TOPIC to the exact string in JSON.
        sub.on(DEFAULT_JOB_TOPIC, handle_job)

        sub_instances.append(sub)

    try:
        for sub in sub_instances:
            await sub.start()

        while True:
            await asyncio.sleep(3600)
    finally:
        for sub in sub_instances:
            await sub.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    max_concurrency = (
        int(os.getenv(DEFAULT_WORKER_MAX_CONCURRENCY_ENV, "0"))
        or DEFAULT_MAX_CONCURRENCY
    )
    execution_timeout_s = float(os.getenv(DEFAULT_EXECUTION_TIMEOUT_S_ENV, "0")) or None

    HERE = os.path.dirname(os.path.abspath(__file__))
    cfg = WorkerPoolConfig(
        max_concurrency=max_concurrency,
        execution_timeout_s=execution_timeout_s,
        subscription_list_path=os.path.join(HERE, "zmq_subscription_list.json"),
    )
    asyncio.run(run_worker_pool(cfg))
