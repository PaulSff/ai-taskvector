"""
Runtime: run process graphs in topological order (plain execution).

Resolves inputs from connections or params, executes units via the unit registry.
Use run_workflow(path, initial_inputs=..., unit_param_overrides=...) for full control;
run_workflow_file(path) for simple run with no inputs; or `python -m runtime workflow.json [--initial-inputs ...]`.
"""

from runtime.executor import GraphExecutor
from runtime.run import run_workflow, run_workflow_file

__all__ = ["GraphExecutor", "run_workflow", "run_workflow_file"]
