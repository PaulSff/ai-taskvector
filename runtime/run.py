"""
Generic workflow execution: load a workflow file, supply initial_inputs and optional
unit param overrides from the run command (or API), run the graph once, return outputs.
No hardcoded unit ids or parameter names; all supplied via arguments.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.normalizer import load_process_graph_from_file
from runtime.executor import GraphExecutor
from units.register_env_agnostic import register_env_agnostic_units


def run_workflow(
    workflow_path: str | Path,
    *,
    initial_inputs: dict[str, dict[str, Any]] | None = None,
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    format: str | None = None,
) -> dict[str, Any]:
    """
    Load a workflow from file, optionally override unit params, run with initial_inputs, return outputs.

    Args:
        workflow_path: Path to workflow JSON or YAML.
        initial_inputs: Optional { unit_id: { port_name: value } } for units with no upstream (e.g. Inject).
        unit_param_overrides: Optional { unit_id: { param_name: value } } to merge into each unit's params.
        format: Optional format hint ('dict'|'yaml'|'node_red'|...); inferred from suffix if None.

    Returns:
        { unit_id: { port_name: value, ... }, ... } for every unit in the graph.
    """
    register_env_agnostic_units()

    path = Path(workflow_path)
    if not path.is_file():
        raise FileNotFoundError(f"Workflow file not found: {path}")

    graph = load_process_graph_from_file(path, format=format or "dict")

    if unit_param_overrides:
        new_units = []
        for u in graph.units:
            over = unit_param_overrides.get(u.id)
            if over and isinstance(over, dict):
                new_units.append(u.model_copy(update={"params": {**(u.params or {}), **over}}))
            else:
                new_units.append(u)
        graph = graph.model_copy(update={"units": new_units})

    executor = GraphExecutor(graph)
    return executor.execute(initial_inputs=initial_inputs or {})


def run_workflow_file(path: str | Path, format: str | None = None) -> dict[str, Any]:
    """
    Load a workflow from file, run once with no initial_inputs, return outputs.
    Backward-compatible wrapper; for full control use run_workflow().
    """
    return run_workflow(path, initial_inputs=None, unit_param_overrides=None, format=format)


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
    parser.add_argument(
        "workflow",
        type=Path,
        help="Path to workflow JSON or YAML",
    )
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

    out = run_workflow(
        args.workflow,
        initial_inputs=initial_inputs,
        unit_param_overrides=unit_param_overrides,
        format=args.format,
    )

    out_json = json.dumps(out, indent=2, default=str)
    if args.output is not None:
        args.output.write_text(out_json)
    else:
        print(out_json)


if __name__ == "__main__":
    main()
