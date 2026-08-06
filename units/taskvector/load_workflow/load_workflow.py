"""
LoadWorkflow unit: load a process graph from a file path (wraps core.normalizer.load_process_graph_from_file).

Input: path (str) — file path to workflow JSON/YAML.
Output: graph (Any) — normalized graph as dict; error (str) — message on failure.
Params: format (optional) — "dict" | "yaml" | "node_red" | "n8n" | etc.; None = infer from suffix.
Used by the GUI so it can load workflows via a workflow instead of calling Core directly.
"""
from __future__ import annotations

from typing import Any, Literal, cast

from units.registry import UnitSpec, register_unit

LOAD_WORKFLOW_INPUT_PORTS = [("path", "str")]
LOAD_WORKFLOW_OUTPUT_PORTS = [("graph", "Any"), ("error", "str")]


FormatProcess = Literal["yaml", "dict", "node_red", "template", "pyflow"]

def _load_workflow_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    path_val = inputs.get("path") or params.get("path")
    if not path_val or not isinstance(path_val, str):
        return ({"graph": None, "error": "LoadWorkflow: path missing"}, state)

    path_str = path_val.strip()

    fmt_raw = params.get("format")
    fmt: FormatProcess | None = None
    if isinstance(fmt_raw, str):
        candidate = fmt_raw.strip()
        if candidate in {"yaml", "dict", "node_red", "template", "pyflow"}:
            fmt = cast(FormatProcess, candidate)

    try:
        from core.normalizer import load_process_graph_from_file

        pg = load_process_graph_from_file(path_str, format=fmt)
        graph = pg.model_dump(by_alias=True) if hasattr(pg, "model_dump") else pg
        return ({"graph": graph, "error": None}, state)
    except FileNotFoundError as e:
        return ({"graph": None, "error": str(e)[:200]}, state)
    except (TypeError, ValueError, RuntimeError) as e:
        return ({"graph": None, "error": str(e)[:200]}, state)


def register_load_workflow() -> None:
    register_unit(UnitSpec(
        type_name="LoadWorkflow",
        input_ports=LOAD_WORKFLOW_INPUT_PORTS,
        output_ports=LOAD_WORKFLOW_OUTPUT_PORTS,
        step_fn=_load_workflow_step,
        environment_tags=["taskvector"],
        environment_tags_are_agnostic=False,
        description="Load process graph from file path (wraps core.normalizer.load_process_graph_from_file). Output: graph dict, error.",
    ))


__all__ = ["LOAD_WORKFLOW_INPUT_PORTS", "LOAD_WORKFLOW_OUTPUT_PORTS", "register_load_workflow"]
