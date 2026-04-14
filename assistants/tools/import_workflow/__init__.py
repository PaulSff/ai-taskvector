"""``import_workflow`` graph edit: prompt line, Import_workflow graph path, post-apply chat strings.

There is no ``run_import_workflow_follow_up`` in ``assistants.tools.registry`` — import is not a
``parser_output`` tool in the ordered follow-up chain; post-apply rounds use ``follow_ups`` strings only.
"""
from __future__ import annotations

from pathlib import Path

from assistants.tools.workflow_path import get_tool_workflow_path


def import_workflow_graph_path() -> Path:
    """Absolute path to the single-unit Import_workflow JSON (from ``tool.yaml`` ``workflow``)."""
    return get_tool_workflow_path("import_workflow")


__all__ = ["import_workflow_graph_path"]
