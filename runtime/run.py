"""
Plain graph execution: load a workflow file and run the graph once.
No training, no steps — just execute the graph and return outputs.
"""
from pathlib import Path
from typing import Any

from runtime.executor import GraphExecutor
from core.normalizer import load_process_graph_from_file


def run_workflow_file(path: str | Path, format: str | None = None) -> dict[str, Any]:
    """
    Load a workflow from file, run the graph once, return unit outputs.

    path: path to workflow JSON or YAML
    format: optional format hint ('yaml'|'node_red'|'dict'|etc.); inferred from suffix if None

    Returns: { unit_id: { port_name: value, ... }, ... }
    """
    graph = load_process_graph_from_file(path, format=format)
    executor = GraphExecutor(graph)
    return executor.execute()
