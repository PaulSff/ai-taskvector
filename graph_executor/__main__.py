"""
Run a workflow file: plain graph execution.

  python -m graph_executor workflow.json
  python -m graph_executor workflow.yaml
"""
import argparse
import json
import sys
from pathlib import Path

from graph_executor.run import run_workflow_file


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute a workflow graph once (plain execution, no training)."
    )
    parser.add_argument(
        "workflow",
        type=Path,
        help="Path to workflow JSON or YAML file",
    )
    parser.add_argument(
        "--format",
        choices=["yaml", "node_red", "dict", "template", "pyflow", "ryven", "n8n"],
        default=None,
        help="Input format (default: infer from file suffix)",
    )
    args = parser.parse_args()

    if not args.workflow.exists():
        print(f"Error: file not found: {args.workflow}", file=sys.stderr)
        sys.exit(1)

    try:
        outputs = run_workflow_file(args.workflow, format=args.format)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Serialize for JSON: convert non-JSON-serializable values to str where needed
    def _serialize(obj: object) -> object:
        if isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_serialize(x) for x in obj]
        if isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        return str(obj)

    out = _serialize(outputs)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    _main()
