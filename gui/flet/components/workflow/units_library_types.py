"""
Resolve unit and pipeline type lists from the units_library workflow (no core types in callers).

Run units_library_workflow.json with graph_summary dict; parse the UnitsLibrary output
to get the filtered unit types and pipeline types for the graph. Used by the Add Node
dialog to avoid depending on core.schemas or core.graph.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# Library workflow lives next to this module under gui/flet/components/workflow/
_THIS_DIR = Path(__file__).resolve().parent
UNITS_LIBRARY_WORKFLOW_PATH = _THIS_DIR / "units_library_workflow.json"


def _parse_units_library_text(text: str) -> tuple[list[str], list[str]]:
    """
    Parse the formatted Units Library string into unit type names and pipeline type names.

    Format: unit lines "TypeName : description", then separator "--", then pipeline lines.
    """
    unit_types: list[str] = []
    pipeline_types: list[str] = []
    in_pipeline_section = False
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("---") or "Units Library" in line or "Environments" in line or "Graph environments" in line:
            continue
        if line == "--":
            in_pipeline_section = True
            continue
        if " : " in line:
            type_name = line.split(" : ", 1)[0].strip()
            if not type_name:
                continue
            if in_pipeline_section:
                pipeline_types.append(type_name)
            else:
                unit_types.append(type_name)
    return (unit_types, pipeline_types)


def get_units_library_type_lists(graph_summary_dict: dict[str, Any]) -> tuple[list[str], list[str]]:
    """
    Run the units_library workflow with graph_summary and return (unit_types, pipeline_types).

    Uses only the UnitsLibrary canonical unit; no dependency on core types. Returns
    the same filtered list that the workflow designer prompt sees.
    """
    if not UNITS_LIBRARY_WORKFLOW_PATH.is_file():
        return ([], [])

    from runtime.run import run_workflow

    try:
        outputs = run_workflow(
            UNITS_LIBRARY_WORKFLOW_PATH,
            initial_inputs={"inject_graph_summary": {"data": graph_summary_dict}},
        )
    except Exception:
        return ([], [])

    data = outputs.get("units_library", {}).get("data")
    if not isinstance(data, str) or not data.strip():
        return ([], [])

    return _parse_units_library_text(data)


__all__ = ["get_units_library_type_lists", "UNITS_LIBRARY_WORKFLOW_PATH"]
