"""
Graph executor: runs process graphs in topological order (ComfyUI-style).

Resolves inputs from connections or params, executes units via the unit registry,
and produces outputs for observation/action mapping.
"""

from graph_executor.executor import GraphExecutor

__all__ = ["GraphExecutor"]
