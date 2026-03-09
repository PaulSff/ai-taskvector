"""
Runtime: run process graphs in topological order (plain execution).

Resolves inputs from connections or params, executes units via the unit registry.
Use run_workflow_file(path) or `python -m runtime workflow.json` to run a workflow once.
"""

from runtime.executor import GraphExecutor
from runtime.run import run_workflow_file

__all__ = ["GraphExecutor", "run_workflow_file"]
