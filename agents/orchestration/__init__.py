"""Orchestration workflows for agent-messenger integration."""

from __future__ import annotations

from pathlib import Path


def orchestration_workflow_path() -> Path:
    """Return the absolute path to orchestration_workflow.json."""
    return Path(__file__).parent / "orchestration_workflow.json"


__all__ = ["orchestration_workflow_path"]
