"""
Graph executor: run process graphs in topological order (plain execution).

Resolves inputs from connections or params, executes units via the unit registry.
Use run_workflow_file(path) or `python -m graph_executor workflow.json` to run a workflow once.
"""

from graph_executor.executor import GraphExecutor
from graph_executor.run import run_workflow_file

__all__ = ["GraphExecutor", "run_workflow_file"]
