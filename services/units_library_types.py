"""
Resolve unit and pipeline entries from the units_library workflow (no core types in callers).

Run units_library_workflow.json with graph_summary dict; parse the UnitsLibrary output
into ``(type_name, description)`` pairs for the Add Node dialog (and any caller that needs
registry blurbs). Used to avoid depending on core.schemas or core.graph.
"""

from __future__ import annotations

from core.schemas.primitives import (
    Data,
    JsonObject,
    WorkflowInputs,
    WorkflowOutputs,
    is_json_object,
    require_json_object_from_object,
)
from config.settings import UNITS_LIBRARY_WORKFLOW_PATH


def _parse_units_library_text(
    text: str,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
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
        if (
            not line
            or line.startswith("---")
            or "Units Library" in line
            or "Environments" in line
            or "Graph environments" in line
        ):
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
    graph_summary_dict: Data,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """
    Run the units_library workflow with graph_summary and return
    ``(unit_entries, pipeline_entries)`` where each entry is
    ``(type_name, description)``.
    """
    if not UNITS_LIBRARY_WORKFLOW_PATH.is_file():
        return ([], [])

    from runtime.run import run_workflow

    try:
        graph_summary: JsonObject = require_json_object_from_object(
            graph_summary_dict,
            field="graph_summary_dict",
        )

        initial_inputs: WorkflowInputs = {
            "inject_graph_summary": {
                "data": graph_summary,
            },
        }

        outputs: WorkflowOutputs = run_workflow(
            UNITS_LIBRARY_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
        )
    except (OSError, FileNotFoundError, ValueError, TypeError):
        return ([], [])

    units_library_output = outputs.get("units_library")

    if not is_json_object(units_library_output):
        return ([], [])

    data = units_library_output.get("data")

    if not isinstance(data, str) or not data.strip():
        return ([], [])

    return _parse_units_library_text(data)



def get_add_node_type_lists(
    graph_summary_dict: Data,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """
    Unit/pipeline types for the Add Node dialog: all environments, runtime-filtered.

    Unlike ``get_units_library_type_lists`` (agent prompt), this includes every registered
    environment-specific unit so users can add web, messengers, data_bi, etc. without
    ``add_environment`` first.
    """
    from units.canonical.units_library.library_builder import collect_unit_type_entries

    try:
        return collect_unit_type_entries(
            graph_summary_dict,
            restrict_to_graph_environments=False,
        )
    except (OSError, FileNotFoundError):
        return ([], [])
    except (ValueError, TypeError):
        return ([], [])


__all__ = [
    "get_add_node_type_lists",
    "get_units_library_type_lists",
]
