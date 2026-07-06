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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from gui.components.settings import (
    get_workflow_project_name,
    get_workflow_save_dir,
)

# ---- Local constants ----
_WORKFLOW_DIR = Path(__file__).resolve().parents[2] / "components" / "workflow_tab"

AUTO_IMPORT_WORKFLOW_PATH = (
    _WORKFLOW_DIR / "workflows" / "import_workflows" / "auto_import_workflow.json"
)
NEW_FLOW_TEMPLATE_PATH = (
    _WORKFLOW_DIR / "workflows" / "import_workflows" / "new_flow_template.json"
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
    workflow_json_path: str, initial_inputs: dict[str, Any]
) -> dict[str, Any]:
    """
    Async wrapper around your sync runtime. Uses a thread so the event loop isn't blocked.
    """
    from runtime.run import run_workflow

    def _run() -> dict[str, Any]:
        outputs = run_workflow(
            workflow_json_path,
            initial_inputs=initial_inputs,
            format="dict",
        )
        return outputs or {}

    return await asyncio.to_thread(_run)


@dataclass(frozen=True)
class ImportResult:
    graph: dict | None
    error: str
    picked_workflow_path: str


async def run_auto_import_workflow_async(
    raw_data: dict | list,
) -> tuple[dict | None, str]:
    """
    Async version of your run_auto_import_workflow(raw_data).
    """
    if not AUTO_IMPORT_WORKFLOW_PATH.exists():
        return (None, f"Workflow file not found: {AUTO_IMPORT_WORKFLOW_PATH}")

    initial_inputs = {DEFAULT_INJECT_KEY: {"data": raw_data}}

    try:
        outputs = await _run_workflow_async(
            str(AUTO_IMPORT_WORKFLOW_PATH),
            initial_inputs=initial_inputs,
        )
    except Exception as e:
        return (None, str(e))

    iw = outputs.get("import_workflow") or {}
    err = iw.get("error") or ""
    graph = iw.get("graph")
    return (graph, err or "")


async def import_latest_workflow_graph_async() -> ImportResult:
    """
    1) Resolve workflow save dir (for the configured project).
    2) Pick latest: {project}_workflow_YY-MM-DD-HHMMSS.json
       else fall back to new_flow_template.json
    3) Run auto_import_workflow.json with the chosen workflow JSON content injected
       and return the produced process graph.
    """
    workflow_root = get_workflow_save_dir()  # e.g. .../my_workflows/my_project/
    project_name = get_workflow_project_name()  # <- replaced derivation

    latest = _pick_latest_workflow_json(workflow_root, project_name)
    if latest is not None:
        picked_path = latest
    else:
        picked_path = NEW_FLOW_TEMPLATE_PATH

    # Log the path we decided to import
    logger.info("[workflow_manager] Importing latest workflow: %s", picked_path)

    if not picked_path.exists():
        return ImportResult(
            graph=None,
            error=f"Workflow file not found: {picked_path}",
            picked_workflow_path=str(picked_path),
        )

    # Load selected workflow JSON
    import json

    try:
        with picked_path.open("r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception as e:
        return ImportResult(
            graph=None,
            error=f"Failed to load workflow JSON '{picked_path}': {e}",
            picked_workflow_path=str(picked_path),
        )

    graph, err = await run_auto_import_workflow_async(raw_data)
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
