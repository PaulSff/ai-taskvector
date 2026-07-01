"""
Async worker pool that consumes ZMQ “job” messages and executes each requested workflow in a separate spawned subprocess.

For each incoming job:
1) Validate payload fields (run_id, workflow_path, inputs/overrides, response_endpoint, execution timeout).
2) Spawn a subprocess that runs `run_workflow(...)` with the provided `run_id`.
   - If `response_endpoint` is provided, `run_workflow` publishes streamed tokens plus the final result or error to ZMQ itself.
3) The asyncio handler waits for the subprocess to finish (via an inter-process Queue) to log success/failure.
4) Concurrency is limited with an asyncio semaphore (`max_concurrency`); extra jobs wait their turn.

The server runs indefinitely, starting all configured ZMQ subscribers from `zmq_subscription_list.json` and stopping them on shutdown.
"""

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

DEFAULT_JOB_TOPIC = ZmqTopics().job

GREEN = "\033[92m"
RESET = "\033[0m"


@dataclass(frozen=True)
class WorkerPoolConfig:
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    rcvtimeo_ms: int = DEFAULT_RCVTIMEO_MS
    execution_timeout_s: Optional[float] = None
    subscription_list_path: str = DEFAULT_SUB_LIST_PATH


shutting_down = asyncio.Event()
shutdown_counter = 0


def _load_subscriptions_from_json(path: str) -> list[tuple[str, str, tuple[str, ...]]]:
    """
    JSON:
    {
      "subscriptions": [
        { "name": "...", "sub_endpoint": "tcp://...", "topic_idx": "0" },
        ...
      ],
      "topics": ["job", "result", ...]
    }

    Returns list of (name, sub_endpoint, topics_tuple_for_that_subscriber).
    """
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    topics_arr = data.get("topics") or []
    subs = data.get("subscriptions") or []

    if not isinstance(topics_arr, list) or not isinstance(subs, list):
        return []

    out: list[tuple[str, str, tuple[str, ...]]] = []
    for item in subs:
        if not isinstance(item, dict):
            continue

        name = item.get("name")
        sub_endpoint = item.get("sub_endpoint")
        topic_idx = item.get("topic_idx")

        if not isinstance(name, str):
            continue
        if not isinstance(sub_endpoint, str):
            continue

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

        out.append((name, sub_endpoint, (topic_name,)))

    return out


def _run_job_in_subprocess(
    *,
    q: Any,  # unused; kept for signature symmetry if you want to evolve
    run_id: str,
    workflow_path: Optional[str],
    workflow_graph: Optional[dict[str, Any]],
    initial_inputs: Optional[dict[str, Any]],
    unit_param_overrides: Optional[dict[str, Any]],
    format: Optional[str],
    response_endpoint: Optional[str],
    execution_timeout_s: Optional[float],
) -> dict[str, Any]:
    zmq_publisher = None
    if response_endpoint:
        zmq_publisher = ZmqPublisher(pub_endpoint=response_endpoint, topics=ZmqTopics())

    if (workflow_path is None) == (workflow_graph is None):
        raise ValueError("Provide exactly one of workflow_path or workflow_graph")

    if workflow_path is not None:
        return run_workflow(
            workflow_path=workflow_path,
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            execution_timeout_s=execution_timeout_s,
            run_id=run_id,
            zmq_publisher=zmq_publisher,
        )

    return run_workflow(
        workflow_graph=workflow_graph,
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
    workflow_path: Optional[str],
    workflow_graph: Optional[dict[str, Any]],
    initial_inputs: Optional[dict[str, Any]],
    unit_param_overrides: Optional[dict[str, Any]],
    format_hint: Optional[str],
    response_endpoint: Optional[str],
    execution_timeout_s: Optional[float],
) -> None:
    try:
        out = _run_job_in_subprocess(
            q=q,
            run_id=run_id,
            workflow_path=workflow_path,
            workflow_graph=workflow_graph,
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

    if not subs:
        raise RuntimeError(
            f"No valid subscriptions found in {cfg.subscription_list_path}"
        )

    sub_instances: list[ZmqSubscriber] = []

    logger.info(
        "Worker pool started; subscribers=%s rcvtimeo_ms=%s", len(subs), cfg.rcvtimeo_ms
    )
    for name, ep, topics in subs:
        logger.info("  subscribing name=%s endpoint=%s topics=%s", name, ep, topics)

    ctx = get_context("spawn")
    sem = asyncio.Semaphore(cfg.max_concurrency)

    async def handle_job(topic: str, payload: Dict[str, Any]) -> None:
        async with sem:
            logger.info(
                "Job received topic=%s payload_keys=%s", topic, list(payload.keys())
            )

            run_id = payload.get("run_id")
            workflow_path = payload.get("workflow_path")
            workflow_graph = payload.get("workflow_graph")

            initial_inputs = payload.get("initial_inputs")
            unit_param_overrides = payload.get("unit_param_overrides")
            format_hint = payload.get("format")
            response_endpoint = payload.get("response_endpoint")

            # Validate run_id
            if not isinstance(run_id, str):
                logger.error(
                    "Invalid job payload (missing/invalid run_id): %r", payload
                )
                return

            workflow_path_ok = isinstance(workflow_path, str)
            workflow_graph_ok = isinstance(workflow_graph, dict)

            # Must provide exactly one
            if (workflow_path_ok and workflow_graph_ok) or (
                not workflow_path_ok and not workflow_graph_ok
            ):
                logger.error(
                    "Invalid job payload (provide exactly one of workflow_path or workflow_graph): %r",
                    payload,
                )
                return

            # Validate other optional fields
            if initial_inputs is not None and not isinstance(initial_inputs, dict):
                logger.error(
                    "Invalid job payload (initial_inputs must be object/map): %r",
                    payload,
                )
                return

            if unit_param_overrides is not None and not isinstance(
                unit_param_overrides, dict
            ):
                logger.error(
                    "Invalid job payload (unit_param_overrides must be object/map): %r",
                    payload,
                )
                return

            if response_endpoint is not None and not isinstance(response_endpoint, str):
                logger.error(
                    "Invalid job payload (response_endpoint must be string): %r",
                    payload,
                )
                return

            # Optional per-job execution timeout override
            execution_timeout_s = cfg.execution_timeout_s
            per_job_timeout = payload.get("execution_timeout_s")
            if per_job_timeout is not None:
                if isinstance(per_job_timeout, (int, float)):
                    execution_timeout_s = float(per_job_timeout)
                else:
                    logger.error(
                        "Invalid job payload (execution_timeout_s must be number): %r",
                        payload,
                    )
                    return

            workflow_path_for_job: Optional[str] = (
                workflow_path if workflow_path_ok else None
            )
            workflow_graph_for_job: Optional[dict[str, Any]] = (
                workflow_graph if workflow_graph_ok else None
            )

            logger.info(
                "Starting job run_id=%s selector=%s response_endpoint=%s",
                run_id,
                "workflow_path"
                if workflow_path_for_job is not None
                else "workflow_graph",
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
                    workflow_path=workflow_path_for_job,
                    workflow_graph=workflow_graph_for_job,
                    initial_inputs=initial_inputs,
                    unit_param_overrides=unit_param_overrides,
                    format_hint=format_hint,
                    response_endpoint=response_endpoint,
                    execution_timeout_s=execution_timeout_s,
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
                        "%sJob finished OK%s run_id=%s response_endpoint=%s",
                        GREEN,
                        RESET,
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

    for name, ep, topics in subs:
        sub = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=ep,
                topics=topics,
                accept_topics=None,
                rcvtimeo_ms=cfg.rcvtimeo_ms,
            )
        )
        sub.on(DEFAULT_JOB_TOPIC, handle_job)
        sub_instances.append(sub)

    shutting_down_steps = 0

    def log_shutdown_step():
        nonlocal shutting_down_steps
        shutting_down_steps += 1
        logger.info("Shutting down… %d", shutting_down_steps)

    try:
        for sub in sub_instances:
            await sub.start()

        logger.info("%sserver is ready%s", GREEN + "[workflow_server]" + RESET, RESET)

        stop_event = asyncio.Event()
        try:
            await stop_event.wait()  # cancelled on Ctrl+C / outer task cancel
        except asyncio.CancelledError:
            pass
    finally:
        log_shutdown_step()
        for sub in sub_instances:
            await sub.stop()
            log_shutdown_step()


if __name__ == "__main__":

    class ColorFormatter(logging.Formatter):
        COLORS = {
            logging.DEBUG: "\033[90m",  # gray
            logging.INFO: "\033[94m",  # blue
            logging.WARNING: "\033[93m",  # yellow
            logging.ERROR: "\033[91m",  # red
            logging.CRITICAL: "\033[95m",  # magenta
        }
        RESET = "\033[0m"

        def format(self, record):
            color = self.COLORS.get(record.levelno, "")
            msg = super().format(record)
            return f"{color}{msg}{self.RESET}"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(ColorFormatter("[%(levelname)s] %(name)s: %(message)s"))

    root.handlers.clear()
    root.addHandler(handler)

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
