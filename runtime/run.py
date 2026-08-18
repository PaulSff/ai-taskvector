from __future__ import annotations

import argparse
import json
import logging
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from threading import Thread
from typing import Any, cast

from core.normalizer import FormatProcess, load_process_graph_from_file
from runtime.executor import GraphExecutor
from runtime.stream_ui_signals import inline_status_stream_chunk
from services.logging import setup_colored_logging
from services.zmq import ZmqPublisher, ZmqTopics
from units.registry import ensure_full_unit_registry

logger = setup_colored_logging(logging.INFO)

INLINE_STATUS_FOR_STREAMING = "Thinking..."


class WorkflowTimeoutError(Exception):
    """Raised when one-shot workflow execution exceeds its timeout."""

    def __init__(self, timeout_s: float, message: str = "") -> None:
        self.timeout_s = timeout_s
        super().__init__(
            message or f"Workflow execution timed out after {timeout_s}s"
        )


def run_workflow(
    workflow_path: str | Path | None = None,
    *,
    workflow_graph: dict[str, Any] | None = None,
    initial_inputs: dict[str, dict[str, Any]] | None = None,
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    format: FormatProcess | None = None,
    execution_timeout_s: float | None = None,
    keep_alive: bool = False,
    stream_callback: Callable[[str], None] | None = None,
    update_callback: Callable[[dict[str, dict[str, Any]]], None] | None = None,
    run_id: str | None = None,
    zmq_publisher: ZmqPublisher | None = None,
    send_job_message: bool = False,
) -> dict[str, Any]:
    """
    Load a workflow from file, optionally override unit params, run with initial_inputs, return outputs.

    Args:
        workflow_path: Path to workflow JSON or YAML.
        workflow_graph: In-memory workflow graph dict.
        initial_inputs: Optional { unit_id: { port_name: value } } for units with no upstream (e.g. Inject).
        unit_param_overrides: Optional { unit_id: { param_name: value } } to merge into each unit's params.
        format: Optional format hint ('dict'|'yaml'|'node_red'|...); inferred from suffix if None.
        execution_timeout_s: If set, abort the run after this many seconds (timeout then drop). Prevents
            hanging when a unit (e.g. LLM, RAG) never responds. Raises WorkflowTimeoutError on timeout.
        stream_callback: Optional callable(str). When the graph runs an LLMAgent unit, each streamed
            token chunk is passed here (called from executor thread; schedule UI updates on main thread).
            Also passed to RunWorkflow and Chameleon; Chameleon with ``stream_outputs`` true emits
            prefixed JSON step chunks (see ``runtime.stream_ui_signals.chameleon_stream_chunk``).
        run_id: Optional externally supplied run id used for ZMQ messages.
        zmq_publisher: Optional ZMQ publisher. If set, token chunks and the final result/error are published.

    Returns:
        { unit_id: { port_name: value, ... }, ... } for every unit in the graph.

    In keep-alive mode, GraphExecutor performs the initial execution, waits
    for wakeup events, reruns affected downstream nodes, publishes updates,
    and returns the latest outputs when stopped or timed out.

    The execution flow becomes:

    execute()
      ├─ initial step
      ├─ return immediately if keep_alive=False
      └─ wait if keep_alive=True
           ├─ DelayLoop timer fires
           ├─ graph_wakeup_callback queues event
           ├─ wakeup consumer reruns downstream graph
           ├─ update_callback receives new outputs
           └─ execute() returns on stop or timeout
    """
    ensure_full_unit_registry()

    if (workflow_path is None) == (workflow_graph is None):
        raise ValueError("Provide exactly one of workflow_path or workflow_graph")

    if workflow_path is not None:
        path = Path(workflow_path).resolve()

        if not path.is_file():
            raise FileNotFoundError(f"Workflow file not found: {path}")

        graph = load_process_graph_from_file(
            path,
            format=format or "dict",
        )
        workflow_path_for_messages: str | None = str(path)
        workflow_graph_for_messages: dict[str, Any] | None = None
    else:
        graph = cast(Any, workflow_graph)
        workflow_path_for_messages = None
        workflow_graph_for_messages = cast(dict[str, Any], workflow_graph)

    try:
        from units.canonical import register_canonical_units

        register_canonical_units()
    except ImportError:
        pass
    except Exception:
        logger.exception("Failed to register canonical units")
        raise

    if unit_param_overrides:
        if not hasattr(graph, "units"):
            raise TypeError(
                "Unsupported workflow_graph type: expected a ProcessGraph-like object with .units"
            )

        updated_units = []

        for unit in graph.units:
            overrides = unit_param_overrides.get(unit.id)

            if overrides and isinstance(overrides, dict):
                updated_units.append(
                    unit.model_copy(
                        update={
                            "params": {
                                **(unit.params or {}),
                                **overrides,
                            }
                        }
                    )
                )
            else:
                updated_units.append(unit)

        graph = graph.model_copy(update={"units": updated_units})

    def _try_register(register_fn_path: str) -> None:
        module_name, function_name = register_fn_path.rsplit(".", 1)

        try:
            module = __import__(
                module_name,
                fromlist=[function_name],
            )
            getattr(module, function_name)()
        except ImportError:
            pass

    _try_register("units.data_bi.register_data_bi_units")
    _try_register("units.web.register_web_units")
    _try_register("units.messengers.register_messengers_units")
    _try_register("units.rag.register_rag_units")

    executor = GraphExecutor(graph)
    init = initial_inputs or {}
    run_id = run_id or uuid.uuid4().hex

    token_callback: Callable[[str], None] | None = stream_callback

    if zmq_publisher is not None:

        def _wrapped_token_callback(token: str) -> None:
            try:
                zmq_publisher.publish_token(
                    run_id=run_id,
                    token=token,
                )
            except (OSError, ConnectionError, TimeoutError) as error:
                logger.warning("ZMQ publish_token failed: %s", error)

            if stream_callback is not None:
                stream_callback(token)

        token_callback = _wrapped_token_callback

    def on_graph_update(
        outputs: dict[str, dict[str, Any]],
    ) -> None:
        """
        Called after the initial execution and after each keep-alive rerun.
        """
        if update_callback is not None:
            try:
                update_callback(outputs)
            except Exception:
                logger.exception("Workflow update callback failed")

        if zmq_publisher is not None:
            try:
                zmq_publisher.publish_update_batch(
                    {
                        "run_id": run_id,
                        "outputs": outputs,
                        "update": True,
                        "ts": time.time(),
                    }
                )
            except (OSError, ConnectionError, TimeoutError) as error:
                logger.warning(
                    "ZMQ publish_update_batch failed: %s",
                    error,
                )

    if zmq_publisher is not None and send_job_message:
        try:
            zmq_publisher.publish_job(
                run_id=run_id,
                workflow_path=workflow_path_for_messages,
                workflow_graph=workflow_graph_for_messages,
                format=cast(str | None, format),
                initial_inputs=initial_inputs,
                unit_param_overrides=unit_param_overrides,
                execution_timeout_s=execution_timeout_s,
            )
        except Exception:
            logger.exception("Failed to publish job message via ZMQ")
            raise

    try:
        if stream_callback is not None:
            try:
                stream_callback(
                    inline_status_stream_chunk(
                        INLINE_STATUS_FOR_STREAMING
                    )
                )
            except (OSError, ConnectionError, TimeoutError) as error:
                logger.warning(
                    "stream_callback failed while sending inline status: %s",
                    error,
                )

        if keep_alive:
            # GraphExecutor owns the long-polling lifecycle.
            outputs = executor.execute(
                initial_inputs=init,
                stream_callback=token_callback,
                keep_alive=True,
                execution_timeout_s=execution_timeout_s,
                update_callback=on_graph_update,
            )


        elif execution_timeout_s is not None and execution_timeout_s > 0:
            result_ref: list[dict[str, Any]] = []
            exception_ref: list[BaseException] = []

            def execute_once() -> None:
                try:
                    result_ref.append(
                        executor.execute(
                            initial_inputs=init,
                            stream_callback=token_callback,
                            update_callback=on_graph_update,
                        )
                    )
                except BaseException as error:
                    logger.exception(
                        "Workflow execution failed in worker thread"
                    )
                    exception_ref.append(error)

            worker = Thread(
                target=execute_once,
                daemon=True,
                name=f"workflow-{run_id}",
            )
            worker.start()
            worker.join(timeout=execution_timeout_s)

            if exception_ref:
                raise exception_ref[0]

            if worker.is_alive():
                raise WorkflowTimeoutError(execution_timeout_s)

            if not result_ref:
                raise WorkflowTimeoutError(
                    execution_timeout_s,
                    "Workflow did not complete within timeout (no result).",
                )

            outputs = result_ref[0]

        else:
            outputs = executor.execute(
                initial_inputs=init,
                stream_callback=token_callback,
                update_callback=on_graph_update,
            )


        if zmq_publisher is not None:
            try:
                zmq_publisher.publish_result(
                    run_id=run_id,
                    outputs=outputs,
                )
            except Exception:
                logger.exception("ZMQ publish_result failed")
                raise

        return outputs

    except Exception as error:
        if zmq_publisher is not None:
            try:
                zmq_publisher.publish_error(
                    run_id=run_id,
                    error=str(error),
                )
            except (OSError, ConnectionError, TimeoutError) as publish_error:
                logger.warning(
                    "ZMQ publish_error failed: %s",
                    publish_error,
                )

        raise

    finally:
        try:
            executor.shutdown()
        except Exception:
            logger.exception("executor.shutdown() failed")


def run_workflow_file(
    path: str | Path,
    format: FormatProcess | None = None,
) -> dict[str, Any]:
    """Backward-compatible one-shot workflow runner."""
    return run_workflow(
        path,
        initial_inputs=None,
        unit_param_overrides=None,
        format=format,
    )


def _load_json_arg(value: str) -> dict[str, Any]:
    """Parse JSON from a string or from a file prefixed with '@'."""
    value = value.strip()

    if value.startswith("@"):
        path = Path(value[1:].strip())

        if not path.is_file():
            raise FileNotFoundError(f"JSON file not found: {path}")

        return json.loads(path.read_text())

    return json.loads(value)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run a workflow from file. Supply initial inputs and unit "
            "parameters through arguments."
        )
    )

    _ = parser.add_argument(
        "workflow",
        type=Path,
        help="Path to workflow JSON or YAML",
    )

    _ = parser.add_argument(
        "--initial-inputs",
        type=str,
        default=None,
        metavar="JSON_OR_@PATH",
        help=(
            "JSON object {unit_id: {port: value}}, "
            "or @path to a JSON file"
        ),
    )

    _ = parser.add_argument(
        "--unit-params",
        type=str,
        default=None,
        metavar="JSON_OR_@PATH",
        help=(
            "JSON object {unit_id: {param_name: value}}, "
            "or @path to a JSON file"
        ),
    )

    _ = parser.add_argument(
        "--format",
        type=str,
        default=None,
        choices=["dict", "yaml", "node_red", "pyflow", "n8n"],
        help="Workflow format; inferred from suffix if omitted",
    )

    _ = parser.add_argument(
        "--execution-timeout-s",
        type=float,
        default=None,
        help=(
            "Maximum execution lifetime. In keep-alive mode, return the "
            "latest outputs when the timeout expires."
        ),
    )

    _ = parser.add_argument(
        "--keep-alive",
        action="store_true",
        help=(
            "Keep the executor alive and rerun affected downstream nodes "
            "after graph wakeup events."
        ),
    )

    _ = parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Optional run ID; otherwise a random ID is generated",
    )

    _ = parser.add_argument(
        "--zmq-pub-endpoint",
        type=str,
        default=None,
        metavar="tcp://host:port",
        help="Publish tokens, updates, results, and errors to this endpoint",
    )

    _ = parser.add_argument(
        "--send-job-message",
        action="store_true",
        help="Publish a job request when ZMQ publishing is enabled",
    )

    _ = parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write final outputs to this file; otherwise print to stdout",
    )

    args = parser.parse_args()

    initial_inputs = (
        _load_json_arg(args.initial_inputs)
        if args.initial_inputs is not None
        else None
    )

    unit_param_overrides = (
        _load_json_arg(args.unit_params)
        if args.unit_params is not None
        else None
    )

    run_id = args.run_id or uuid.uuid4().hex

    zmq_publisher = None

    if args.zmq_pub_endpoint is not None:
        zmq_publisher = ZmqPublisher(
            pub_endpoint=args.zmq_pub_endpoint,
            topics=ZmqTopics(),
        )

    try:
        outputs = run_workflow(
            args.workflow,
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format=cast(FormatProcess | None, args.format),
            execution_timeout_s=args.execution_timeout_s,
            keep_alive=args.keep_alive,
            run_id=run_id,
            zmq_publisher=zmq_publisher,
            send_job_message=bool(
                args.send_job_message and zmq_publisher is not None
            ),
        )

        output_json = json.dumps(
            outputs,
            indent=2,
            default=str,
        )

        if args.output is not None:
            args.output.write_text(output_json)
        else:
            print(output_json)

    finally:
        if zmq_publisher is not None:
            close = getattr(zmq_publisher, "close", None)

            if callable(close):
                close()


if __name__ == "__main__":
    main()
