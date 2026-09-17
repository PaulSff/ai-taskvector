# workflow_manager.py
"""
This async workflow manager (importer) finds the newest workflow JSON
in your project’s workflow directory (or falls back to a default template),
runs auto_import_workflow.json to build the process graph, and returns
the imported graph while logging which workflow file was used.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from pydantic import ValidationError

from core.normalizer.shared import to_json_value
from core.schemas import ProcessGraph
from core.schemas.primitives import JsonValue, WorkflowInputs
from config.settings import (
    AUTO_IMPORT_WORKFLOW_PATH,
    NEW_FLOW_TEMPLATE_PATH,
    get_workflow_project_name,
    get_workflow_save_dir,
)

logger = logging.getLogger(__name__)

DEFAULT_INJECT_KEY: Literal["inject_graph"] = "inject_graph"


def _pick_latest_workflow_json(workflows_dir: Path, project_name: str) -> Path | None:
    """
    Expected files:
      my_project_workflow_26-06-15-100922.json
    Pick the latest by the date+time suffix embedded in the filename.
    """
    if not workflows_dir.exists() or not workflows_dir.is_dir():
        return None

    prefix = f"{project_name}_workflow_"
    candidates: list[Path] = [
        p
        for p in workflows_dir.iterdir()
        if p.is_file() and p.name.startswith(prefix) and p.suffix.lower() == ".json"
    ]
    if not candidates:
        return None

    # filename suffix after prefix is: YY-MM-DD-HHMMSS.json
    def sort_key(p: Path) -> str:
        # Compare lexicographically because format is zero-padded YY-MM-DD-HHMMSS
        return p.stem[len(prefix) :]  # "26-06-15-100922"

    return max(candidates, key=sort_key)


async def _run_workflow_async(
    workflow_json_path: str,
    initial_inputs: WorkflowInputs,
) -> dict[str, object]:
    """
    Async wrapper around the synchronous runtime.

    Runs the workflow in a thread so the event loop is not blocked.
    """

    from runtime.run import run_workflow

    def _run() -> dict[str, object]:
        outputs = run_workflow(
            workflow_json_path,
            initial_inputs=initial_inputs,
            format="dict",
        )

        return {
            str(key): value
            for key, value in outputs.items()
        }

    return await asyncio.to_thread(_run)



@dataclass(frozen=True)
class ImportResult:
    graph: ProcessGraph | None
    error: str
    picked_workflow_path: str


async def run_auto_import_workflow_async(
    raw_data: dict[str, JsonValue] | list[JsonValue],
) -> tuple[dict[str, JsonValue] | None, str]:
    """
    Async version of run_auto_import_workflow(raw_data).
    """

    if not AUTO_IMPORT_WORKFLOW_PATH.exists():
        return None, f"Workflow file not found: {AUTO_IMPORT_WORKFLOW_PATH}"

    initial_inputs: WorkflowInputs = {
        DEFAULT_INJECT_KEY: {
            "data": raw_data,
        },
    }

    try:
        outputs = await _run_workflow_async(
            str(AUTO_IMPORT_WORKFLOW_PATH),
            initial_inputs=initial_inputs,
        )
    except (ValueError, KeyError, OSError, TimeoutError) as exc:
        return None, str(exc)

    import_workflow_obj = outputs.get("import_workflow")

    if isinstance(import_workflow_obj, Mapping):
        import_workflow = cast(
            Mapping[str, JsonValue],
            import_workflow_obj,
        )
    else:
        import_workflow: Mapping[str, JsonValue] = {}

    error_obj: JsonValue = import_workflow.get("error")
    error = error_obj.strip() if isinstance(error_obj, str) else ""

    graph_obj: JsonValue = import_workflow.get("graph")

    graph: dict[str, JsonValue] | None = None

    if isinstance(graph_obj, Mapping):
        graph = dict(
            cast(Mapping[str, JsonValue], graph_obj)
        )

    return graph, error


async def import_latest_workflow_graph_async() -> ImportResult:
    """
    1) Resolve workflow save dir for the configured project.
    2) Pick the latest:
       {project}_workflow_YY-MM-DD-HHMMSS.json
       Otherwise fall back to new_flow_template.json.
    3) Run auto_import_workflow.json with the selected workflow JSON
       content injected, then return the produced process graph.
    """
    import json
    from typing import cast

    workflow_root = get_workflow_save_dir()
    project_name = get_workflow_project_name()

    latest = _pick_latest_workflow_json(workflow_root, project_name)
    picked_path = latest if latest is not None else NEW_FLOW_TEMPLATE_PATH

    logger.info(
        "[workflow_manager] Importing latest workflow: %s",
        picked_path,
    )

    if not picked_path.exists():
        return ImportResult(
            graph=None,
            error=f"Workflow file not found: {picked_path}",
            picked_workflow_path=str(picked_path),
        )

    try:
        with picked_path.open("r", encoding="utf-8") as f:
            parsed: object = cast(object, json.load(f))
            raw_data: JsonValue = to_json_value(parsed)

        # run_auto_import_workflow_async() accepts only a JSON object
        # or array, not a scalar JSON value.
        if not isinstance(raw_data, (dict, list)):
            return ImportResult(
                graph=None,
                error=(
                    "Invalid workflow JSON: root value must be a JSON "
                    f"object or array, got {type(raw_data).__name__}"
                ),
                picked_workflow_path=str(picked_path),
            )

    except FileNotFoundError as exc:
        return ImportResult(
            graph=None,
            error=f"Failed to load workflow JSON '{picked_path}': {exc}",
            picked_workflow_path=str(picked_path),
        )
    except PermissionError as exc:
        return ImportResult(
            graph=None,
            error=f"Failed to load workflow JSON '{picked_path}': {exc}",
            picked_workflow_path=str(picked_path),
        )
    except json.JSONDecodeError as exc:
        return ImportResult(
            graph=None,
            error=f"Failed to load workflow JSON '{picked_path}': {exc}",
            picked_workflow_path=str(picked_path),
        )
    except OSError as exc:
        return ImportResult(
            graph=None,
            error=f"Failed to load workflow JSON '{picked_path}': {exc}",
            picked_workflow_path=str(picked_path),
        )

    graph_data, err = await run_auto_import_workflow_async(raw_data)

    if graph_data is None:
        return ImportResult(
            graph=None,
            error=err,
            picked_workflow_path=str(picked_path),
        )

    try:
        graph = ProcessGraph.model_validate(graph_data)
    except ValidationError as exc:
        return ImportResult(
            graph=None,
            error=f"Invalid imported workflow graph: {exc}",
            picked_workflow_path=str(picked_path),
        )

    return ImportResult(
        graph=graph,
        error=err,
        picked_workflow_path=str(picked_path),
    )


# Convenience entrypoint if you want to run it from a sync context
def import_latest_workflow_graph() -> ImportResult:
    return asyncio.run(import_latest_workflow_graph_async())


# Example usage somewhere in your server startup / request handler
# from agents.workflow_importer.latest_importer_async import import_latest_workflow_graph_async
#
# result = await import_latest_workflow_graph_async()
# if result.error:
#     logger.error("Import failed: %s (picked=%s)", result.error, result.picked_workflow_path)
# else:
#     process_graph = result.graph
