"""
Resolve unit and pipeline entries from the units_library workflow (no core types in callers).

Run units_library_workflow.json with graph_summary dict; parse the UnitsLibrary output
into ``(type_name, description)`` pairs for the Add Node dialog (and any caller that needs
registry blurbs). Used to avoid depending on core.schemas or core.graph.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# Library workflow under gui/components/workflow_tab/workflows/assistants_workflows/
_WORKFLOW_PKG_DIR = Path(__file__).resolve().parent.parent
UNITS_LIBRARY_WORKFLOW_PATH = _WORKFLOW_PKG_DIR / "workflows" / "assistants_workflows" / "units_library_workflow.json"


def _parse_units_library_text(text: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """
    Parse the formatted Units Library string into (type_name, description) for units and pipelines.

    Format: unit lines ``TypeName : description`` (optional `` — read_file: …`` suffix stripped for UI),
    then separator ``--``, then pipeline lines with the same shape.
    """
    unit_entries: list[tuple[str, str]] = []
    pipeline_entries: list[tuple[str, str]] = []
    in_pipeline_section = False
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("---") or "Units Library" in line or "Environments" in line or "Graph environments" in line:
            continue
        if line == "--":
            in_pipeline_section = True
            continue
        if " : " in line:
            type_name, rest = line.split(" : ", 1)
            type_name = type_name.strip()
            if not type_name:
                continue
            desc = rest.strip()
            if " — read_file:" in desc:
                desc = desc.split(" — read_file:", 1)[0].strip()
            if not desc:
                desc = type_name
            if in_pipeline_section:
                pipeline_entries.append((type_name, desc))
            else:
                unit_entries.append((type_name, desc))
    return (unit_entries, pipeline_entries)


def get_units_library_type_lists(
    graph_summary_dict: dict[str, Any],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """
    Run the units_library workflow with graph_summary and return
    ``(unit_entries, pipeline_entries)`` where each entry is ``(type_name, description)``.

    Uses only the UnitsLibrary canonical unit; no dependency on core types. Matches the
    filtered list the workflow designer prompt sees (same formatted string, parsed).
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
