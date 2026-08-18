from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import threading
import traceback
from dataclasses import dataclass
from multiprocessing import get_context
from typing import ClassVar, Literal, Protocol, TypeAlias, cast, override

from runtime import run_workflow
from services.zmq import (
    ZmqPublisher,
    ZmqSubscriber,
    ZmqSubscriptionConfig,
    ZmqTopics,
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
    execution_timeout_s: float | None = None
    subscription_list_path: str = DEFAULT_SUB_LIST_PATH

FormatProcess = Literal[
    "yaml",
    "dict",
    "node_red",
    "template",
    "pyflow",
]

JsonValue: TypeAlias = ( # noqa: UP040
    str
    | int
    | float
    | bool
    | None
    | list["JsonValue"]
    | dict[str, "JsonValue"]
)

JsonObject: TypeAlias = dict[str, JsonValue] # noqa: UP040
WorkflowInputs: TypeAlias = dict[str, dict[str, object]]  # noqa: UP040

class ProcessQueue(Protocol):
    def put(self, item: JsonObject) -> None:
        ...

def _load_subscriptions_from_json(
    path: str,
) -> list[tuple[str, str, tuple[str, ...]]]:
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as file:
        raw_data = cast(object, json.load(file))

    if not isinstance(raw_data, dict):
        return []

    data = cast(dict[str, object], raw_data)

    raw_topics = data.get("topics", [])
    raw_subscriptions = data.get("subscriptions", [])

    if not isinstance(raw_topics, list):
        return []

    if not isinstance(raw_subscriptions, list):
        return []

    topics: list[object] = cast(list[object], raw_topics)
    subscriptions: list[object] = cast(list[object], raw_subscriptions)

    topics_arr: list[str] = []

    for raw_topic in topics:
        if not isinstance(raw_topic, str):
            return []

        topics_arr.append(raw_topic)

    result: list[tuple[str, str, tuple[str, ...]]] = []

    for raw_item in subscriptions:
        if not isinstance(raw_item, dict):
            continue

        item = cast(dict[str, object], raw_item)

        name = item.get("name")
        sub_endpoint = item.get("sub_endpoint")
        topic_idx = item.get("topic_idx")

        if not isinstance(name, str):
            continue

        if not isinstance(sub_endpoint, str):
            continue

        index: int | None = None

        if isinstance(topic_idx, int) and not isinstance(topic_idx, bool):
            index = topic_idx
        elif isinstance(topic_idx, str):
            try:
                index = int(topic_idx)
            except ValueError:
                continue

        if index is None or not 0 <= index < len(topics_arr):
            continue

        result.append((name, sub_endpoint, (topics_arr[index],)))

    return result


def _run_job_in_subprocess(
    *,
    q: ProcessQueue,
    run_id: str,
    workflow_path: str | None,
    workflow_graph: JsonObject | None,
    initial_inputs: WorkflowInputs | None,
    unit_param_overrides: WorkflowInputs | None,
    format_hint: FormatProcess | None,
    response_endpoint: str | None,
    execution_timeout_s: float | None,
    keep_alive: bool,
) -> JsonObject:

    """
    Execute one workflow inside the spawned subprocess.
    """
    del q

    zmq_publisher: ZmqPublisher | None = None

    if response_endpoint is not None:
        zmq_publisher = ZmqPublisher(
            pub_endpoint=response_endpoint,
            topics=ZmqTopics(),
        )

    if (workflow_path is None) == (workflow_graph is None):
        raise ValueError(
            "Provide exactly one of workflow_path or workflow_graph"
        )

    if workflow_path is not None:
        return run_workflow(
            workflow_path=workflow_path,
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format=format_hint,
            execution_timeout_s=execution_timeout_s,
            keep_alive=keep_alive,
            run_id=run_id,
            zmq_publisher=zmq_publisher,
        )

    assert workflow_graph is not None

    return run_workflow(
        workflow_graph=workflow_graph,
        initial_inputs=initial_inputs,
        unit_param_overrides=unit_param_overrides,
        format=format_hint,
        execution_timeout_s=execution_timeout_s,
        keep_alive=keep_alive,
        run_id=run_id,
        zmq_publisher=zmq_publisher,
    )


def _proc_entrypoint(
    q: ProcessQueue,
    *,
    run_id: str,
    workflow_path: str | None,
    workflow_graph: JsonObject | None,
    initial_inputs: WorkflowInputs | None,
    unit_param_overrides: WorkflowInputs | None,
    format_hint: FormatProcess | None,
    response_endpoint: str | None,
    execution_timeout_s: float | None,
    keep_alive: bool,
) -> None:

    try:
        outputs = _run_job_in_subprocess(
            q=q,
            run_id=run_id,
            workflow_path=workflow_path,
            workflow_graph=workflow_graph,
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format_hint=format_hint,
            response_endpoint=response_endpoint,
            execution_timeout_s=execution_timeout_s,
            keep_alive=keep_alive,
        )

        q.put(
            {
                "ok": True,
                "outputs": outputs,
            }
        )

    except (
        ValueError,
        TypeError,
        TimeoutError,
        RuntimeError,
        KeyError,
    ) as exc:
        q.put(
            {
                "ok": False,
                "error": (
                    f"{type(exc).__name__}: {exc}\n"
                    f"{traceback.format_exc()}"
                ),
            }
        )


async def run_worker_pool(cfg: WorkerPoolConfig) -> None:
    subscriptions = _load_subscriptions_from_json(
        cfg.subscription_list_path
    )

    if not subscriptions:
        raise RuntimeError(
            "No valid subscriptions found in {cfg.subscription_list_path}"
        )

    subscriber_instances: list[ZmqSubscriber] = []

    logger.info(
        "Worker pool started; subscribers=%s rcvtimeo_ms=%s max_concurrency=%s execution_timeout_s=%s",
        len(subscriptions),
        cfg.rcvtimeo_ms,
        cfg.max_concurrency,
        cfg.execution_timeout_s,
    )

    for name, endpoint, topics in subscriptions:
        logger.info(
            "subscribing name=%s endpoint=%s topics=%s",
            name,
            endpoint,
            topics,
        )

    multiprocessing_context = get_context("spawn")
    semaphore = asyncio.Semaphore(cfg.max_concurrency)

    async def handle_job(
        topic: str,
        payload: dict[str, object],
    ) -> None:
        async with semaphore:
            logger.info(
                "Job received topic=%s payload_keys=%s",
                topic,
                list(payload.keys()),
            )

            run_id = payload.get("run_id")
            workflow_path = payload.get("workflow_path")
            workflow_graph = payload.get("workflow_graph")

            initial_inputs = payload.get("initial_inputs")
            unit_param_overrides = payload.get("unit_param_overrides")
            format_hint = payload.get("format")
            response_endpoint = payload.get("response_endpoint")
            keep_alive = payload.get("keep_alive", False)

            if not isinstance(run_id, str) or not run_id:
                logger.error(
                    "Invalid job payload (missing/invalid run_id): %r",
                    payload,
                )
                return

            workflow_path_is_valid = isinstance(workflow_path, str)
            workflow_graph_is_valid = isinstance(workflow_graph, dict)

            if (
                workflow_path_is_valid and workflow_graph_is_valid
            ) or (
                not workflow_path_is_valid
                and not workflow_graph_is_valid
            ):
                logger.error(
                    "Invalid job payload (provide exactly one of workflow_path or workflow_graph): %r",
                    payload,
                )
                return

            if (
                initial_inputs is not None
                and not isinstance(initial_inputs, dict)
            ):
                logger.error(
                    "Invalid job payload (initial_inputs must be an object/map): %r",
                    payload,
                )
                return

            if (
                unit_param_overrides is not None
                and not isinstance(unit_param_overrides, dict)
            ):
                logger.error(
                    "Invalid job payload (unit_param_overrides must be an object/map): %r",
                    payload,
                )
                return

            if (
                response_endpoint is not None
                and not isinstance(response_endpoint, str)
            ):
                logger.error(
                    "Invalid job payload (response_endpoint must be a string): %r",
                    payload,
                )
                return

            if not isinstance(keep_alive, bool):
                logger.error(
                    "Invalid job payload (keep_alive must be a boolean): %r",
                    payload,
                )
                return

            execution_timeout_s = cfg.execution_timeout_s
            per_job_timeout = payload.get("execution_timeout_s")

            if per_job_timeout is not None:
                if (
                    isinstance(per_job_timeout, bool)
                    or not isinstance(per_job_timeout, (int, float))
                ):
                    logger.error(
                        "Invalid job payload (execution_timeout_s must be a number): %r",
                        payload,
                    )
                    return

                execution_timeout_s = float(per_job_timeout)

                if execution_timeout_s <= 0:
                    logger.error(
                        "Invalid job payload (execution_timeout_s must be greater than zero): %r",
                        payload,
                    )
                    return

            workflow_path_for_job: str | None = (
                workflow_path if workflow_path_is_valid else None
            )

            workflow_graph_for_job: dict[str, object] | None = (
                cast(dict[str, object], workflow_graph)
                if workflow_graph_is_valid
                else None
            )

            logger.info(
                "Starting job run_id=%s selector=%s keep_alive=%s response_endpoint=%s",
                run_id,
                (
                    "workflow_path"
                    if workflow_path_for_job is not None
                    else "workflow_graph"
                ),
                keep_alive,
                response_endpoint,
            )

            loop = asyncio.get_running_loop()
            result_future: asyncio.Future[dict[str, object]] = (
                loop.create_future()
            )

            result_queue = multiprocessing_context.Queue()

            process = multiprocessing_context.Process(
                target=_proc_entrypoint,
                kwargs={
                    "q": result_queue,
                    "run_id": run_id,
                    "workflow_path": workflow_path_for_job,
                    "workflow_graph": workflow_graph_for_job,
                    "initial_inputs": initial_inputs,
                    "unit_param_overrides": unit_param_overrides,
                    "format_hint": format_hint,
                    "response_endpoint": response_endpoint,
                    "execution_timeout_s": execution_timeout_s,
                    "keep_alive": keep_alive,
                },
                daemon=True,
            )

            process.start()

            def wait_for_result() -> None:
                message: dict[str, object]

                try:
                    raw_message = cast(object, result_queue.get())

                    if isinstance(raw_message, dict):
                        typed_message = cast(
                            dict[object, object],
                            raw_message,
                        )

                        message = {
                            str(key): value
                            for key, value in typed_message.items()
                        }
                    else:
                        message = {
                            "ok": False,
                            "error": (
                                "Unexpected worker response type: "
                                f"{type(raw_message).__name__}"
                            ),
                        }

                except (
                    OSError,
                    ValueError,
                    TypeError,
                    RuntimeError,
                ) as exc:
                    message = {
                        "ok": False,
                        "error": (
                            f"{type(exc).__name__}: {exc}\n"
                            f"{traceback.format_exc()}"
                        ),
                    }

                _ = loop.call_soon_threadsafe(
                    _set_future_result_if_pending,
                    result_future,
                    message,
                )


            threading.Thread(
                target=wait_for_result,
                daemon=True,
            ).start()

            try:
                message = await result_future

                if message.get("ok"):
                    logger.info(
                        "%sJob finished OK%s run_id=%s keep_alive=%s response_endpoint=%s",
                        GREEN,
                        RESET,
                        run_id,
                        keep_alive,
                        response_endpoint,
                    )
                else:
                    logger.error(
                        "Job failed run_id=%s keep_alive=%s response_endpoint=%s error=%s",
                        run_id,
                        keep_alive,
                        response_endpoint,
                        message.get("error"),
                    )

            finally:
                process.join(timeout=1)

                if process.is_alive():
                    logger.info(
                        "Terminating still-running worker run_id=%s keep_alive=%s",
                        run_id,
                        keep_alive,
                    )
                    process.terminate()
                    process.join(timeout=1)

                try:
                    result_queue.close()
                    result_queue.join_thread()
                except (OSError, ValueError):
                    pass

    for name, endpoint, topics in subscriptions:
        subscriber = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=endpoint,
                topics=topics,
                accept_topics=None,
                rcvtimeo_ms=cfg.rcvtimeo_ms,
            )
        )

        subscriber.on(DEFAULT_JOB_TOPIC, handle_job)
        subscriber_instances.append(subscriber)

    shutdown_step = 0

    def log_shutdown_step() -> None:
        nonlocal shutdown_step
        shutdown_step += 1
        logger.info("Shutting down… %d", shutdown_step)

    try:
        for subscriber in subscriber_instances:
            await subscriber.start()

        logger.info(
            "%sserver is ready%s",
            f"{GREEN}[workflow_server]{RESET}",
            RESET,
        )

        stop_event = asyncio.Event()

        def request_stop(*_args: object) -> None:
            stop_event.set()

        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, request_stop)
            except NotImplementedError:
                pass

        try:
            _ = await stop_event.wait()
        except asyncio.CancelledError:
            pass

    finally:
        log_shutdown_step()

        for subscriber in subscriber_instances:
            await subscriber.stop()
            log_shutdown_step()


def _set_future_result_if_pending(
    future: asyncio.Future[dict[str, object]],
    result: dict[str, object],
) -> None:
    if not future.done():
        future.set_result(result)


if __name__ == "__main__":
    class ColorFormatter(logging.Formatter):
        COLORS: ClassVar[dict[int, str]] = {
            logging.DEBUG: "\033[90m",
            logging.INFO: "\033[94m",
            logging.WARNING: "\033[93m",
            logging.ERROR: "\033[91m",
            logging.CRITICAL: "\033[95m",
        }

        RESET: ClassVar[str] = "\033[0m"

        @override
        def format(self, record: logging.LogRecord) -> str:
            color = self.COLORS.get(record.levelno, "")
            message = super().format(record)
            return f"{color}{message}{self.RESET}"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(
        ColorFormatter("[%(levelname)s] %(name)s: %(message)s")
    )

    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    configured_max_concurrency = int(
        os.getenv(DEFAULT_WORKER_MAX_CONCURRENCY_ENV, "0")
    )

    max_concurrency = (
        configured_max_concurrency
        if configured_max_concurrency > 0
        else DEFAULT_MAX_CONCURRENCY
    )

    configured_execution_timeout = float(
        os.getenv(DEFAULT_EXECUTION_TIMEOUT_S_ENV, "0")
    )

    execution_timeout_s = (
        configured_execution_timeout
        if configured_execution_timeout > 0
        else None
    )

    here = os.path.dirname(os.path.abspath(__file__))

    config = WorkerPoolConfig(
        max_concurrency=max_concurrency,
        execution_timeout_s=execution_timeout_s,
        subscription_list_path=os.path.join(
            here,
            DEFAULT_SUB_LIST_PATH,
        ),
    )

    asyncio.run(run_worker_pool(config))
