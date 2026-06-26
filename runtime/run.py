from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from threading import Thread
from typing import Any, Callable, cast

from core.normalizer import FormatProcess, load_process_graph_from_file
from runtime.executor import GraphExecutor
from runtime.zmq_messaging import ZmqPublisher, ZmqTopics
from units.registry import ensure_full_unit_registry


class WorkflowTimeoutError(Exception):
    """Raised when workflow execution exceeds execution_timeout_s. Prevents hanging on slow/missing sources."""

    def __init__(self, timeout_s: float, message: str = "") -> None:
        self.timeout_s = timeout_s
        super().__init__(message or f"Workflow execution timed out after {timeout_s}s")


def run_workflow(
    workflow_path: str | Path | None = None,
    *,
    workflow_graph: dict[str, Any] | None = None,
    initial_inputs: dict[str, dict[str, Any]] | None = None,
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    format: FormatProcess | None = None,
    execution_timeout_s: float | None = None,
    stream_callback: Callable[[str], None] | None = None,
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
    """
    ensure_full_unit_registry()

    if (workflow_path is None) == (workflow_graph is None):
        raise ValueError("Provide exactly one of workflow_path or workflow_graph")

    # ---- Load graph (file or in-memory) ----
    if workflow_path is not None:
        path = Path(workflow_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Workflow file not found: {path}")
        graph = load_process_graph_from_file(path, format=format or "dict")
        workflow_graph_path_for_messages: str | None = str(path)
        workflow_graph_for_messages: dict[str, Any] | None = None
    else:
        graph = cast(Any, workflow_graph)
        workflow_graph_path_for_messages = None
        workflow_graph_for_messages = cast(dict[str, Any], workflow_graph)

    # Re-register canonical units so Aggregate, Prompt, etc. have step_fn.
    try:
        from units.canonical import register_canonical_units

        register_canonical_units()
    except Exception:
        pass

    if unit_param_overrides:
        if hasattr(graph, "units"):
            new_units = []
            for u in graph.units:
                over = unit_param_overrides.get(u.id)
                if over and isinstance(over, dict):
                    new_units.append(
                        u.model_copy(update={"params": {**(u.params or {}), **over}})
                    )
                else:
                    new_units.append(u)
            graph = graph.model_copy(update={"units": new_units})
        else:
            raise TypeError(
                "Unsupported workflow_graph type: expected a ProcessGraph-like object with .units"
            )

    # Register optional unit packs used by workflows.
    try:
        from units.data_bi import register_data_bi_units

        register_data_bi_units()
    except Exception:
        pass
    try:
        from units.web import register_web_units

        register_web_units()
    except Exception:
        pass
    try:
        from units.messengers import register_messengers_units

        register_messengers_units()
    except Exception:
        pass
    try:
        from units.rag import register_rag_units

        register_rag_units()
    except Exception:
        pass

    executor = GraphExecutor(graph)
    init = initial_inputs or {}

    if run_id is None:
        run_id = uuid.uuid4().hex

    token_cb: Callable[[str], None] | None = stream_callback
    if zmq_publisher is not None:

        def _wrapped_token_cb(tok: str) -> None:
            try:
                zmq_publisher.publish_token(run_id=run_id, token=tok)
            except Exception:
                pass
            if stream_callback is not None:
                stream_callback(tok)

        token_cb = _wrapped_token_cb

    # ---- Publish job request (file OR in-memory) ----
    if zmq_publisher is not None and send_job_message:
        try:
            zmq_publisher.publish_job(
                run_id=run_id,
                workflow_path=workflow_graph_path_for_messages,
                workflow_graph=workflow_graph_for_messages,
                format=cast(str | None, format),
                initial_inputs=initial_inputs,
                unit_param_overrides=unit_param_overrides,
            )
        except Exception:
            pass

    try:
        if execution_timeout_s is not None and execution_timeout_s > 0:
            result_ref: list[dict[str, Any]] = []
            exc_ref: list[BaseException] = []

            def run() -> None:
                try:
                    out = executor.execute(
                        initial_inputs=init, stream_callback=token_cb
                    )
                    result_ref.append(out)
                except BaseException as e:
                    exc_ref.append(e)

            thread = Thread(target=run, daemon=True)
            thread.start()
            thread.join(timeout=execution_timeout_s)

            if exc_ref:
                raise exc_ref[0]
            if thread.is_alive():
                raise WorkflowTimeoutError(execution_timeout_s)
            if not result_ref:
                raise WorkflowTimeoutError(
                    execution_timeout_s,
                    "Workflow did not complete within timeout (no result).",
                )

            outputs = result_ref[0]
        else:
            outputs = executor.execute(initial_inputs=init, stream_callback=token_cb)

        if zmq_publisher is not None:
            try:
                zmq_publisher.publish_result(run_id=run_id, outputs=outputs)
            except Exception:
                pass

        return outputs

    except BaseException as e:
        if zmq_publisher is not None:
            try:
                zmq_publisher.publish_error(run_id=run_id, error=str(e))
            except Exception:
                pass
        raise

    finally:
        try:
            executor.shutdown()
        except Exception:
            pass


def run_workflow_file(
    path: str | Path, format: FormatProcess | None = None
) -> dict[str, Any]:
    """
    Load a workflow from file, run once with no initial_inputs, return outputs.
    Backward-compatible wrapper; for full control use run_workflow().
    """
    return run_workflow(
        path, initial_inputs=None, unit_param_overrides=None, format=format
    )


def _load_json_arg(value: str) -> dict[str, Any]:
    """Parse JSON from a string. If value starts with @, read from file."""
    s = value.strip()
    if s.startswith("@"):
        path = Path(s[1:].strip())
        if not path.is_file():
            raise FileNotFoundError(f"JSON file not found: {path}")
        return json.loads(path.read_text())
    return json.loads(s)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a workflow from file. Supply initial_inputs and unit params via arguments (no hardcoding)."
    )
    parser.add_argument("workflow", type=Path, help="Path to workflow JSON or YAML")
    parser.add_argument(
        "--initial-inputs",
        type=str,
        default=None,
        metavar="JSON_OR_@PATH",
        help="JSON object { unit_id: { port: value } }, or @path to JSON file",
    )
    parser.add_argument(
        "--unit-params",
        type=str,
        default=None,
        metavar="JSON_OR_@PATH",
        help="JSON object { unit_id: { param_name: value } } to override unit params, or @path",
    )
    parser.add_argument(
        "--format",
        type=str,
        default=None,
        choices=["dict", "yaml", "node_red", "pyflow", "n8n"],
        help="Workflow format; inferred from suffix if omitted",
    )
    parser.add_argument(
        "--execution-timeout-s",
        type=float,
        default=None,
        help="Abort run after this many seconds (then raise WorkflowTimeoutError).",
    )
    parser.add_argument(
        "--run-id", type=str, default=None, help="Optional run id (otherwise random)."
    )

    parser.add_argument(
        "--zmq-pub-endpoint",
        type=str,
        default=None,
        metavar="tcp://host:port",
        help="If set, publish tokens/results/errors to this PUB endpoint.",
    )
    parser.add_argument(
        "--send-job-message",
        action="store_true",
        help="If set and --zmq-pub-endpoint is provided, also publish a job request message.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write outputs JSON to this file (default: print to stdout)",
    )
    args = parser.parse_args()

    initial_inputs = None
    if args.initial_inputs is not None:
        initial_inputs = _load_json_arg(args.initial_inputs)

    unit_param_overrides = None
    if args.unit_params is not None:
        unit_param_overrides = _load_json_arg(args.unit_params)

    run_id = args.run_id or uuid.uuid4().hex

    zmq_publisher = None
    if args.zmq_pub_endpoint is not None:
        zmq_publisher = ZmqPublisher(
            pub_endpoint=args.zmq_pub_endpoint, topics=ZmqTopics()
        )

    out = run_workflow(
        args.workflow,
        initial_inputs=initial_inputs,
        unit_param_overrides=unit_param_overrides,
        format=cast(FormatProcess | None, args.format),
        execution_timeout_s=args.execution_timeout_s,
        run_id=run_id,
        zmq_publisher=zmq_publisher,
        send_job_message=bool(args.send_job_message and zmq_publisher is not None),
    )

    out_json = json.dumps(out, indent=2, default=str)
    if args.output is not None:
        args.output.write_text(out_json)
    else:
        print(out_json)


if __name__ == "__main__":
    main()
