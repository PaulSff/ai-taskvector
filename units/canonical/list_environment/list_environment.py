"""
list_environment: scaffold units/<new_environment_id>/ and register an env loader.

Params: action list_environment, new_environment_id (tag), readme_md.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from units.canonical._scaffold_env import repo_root_containing_units, run_list_environment
from units.registry import UnitSpec, register_unit

LIST_ENV_INPUT_PORTS = [("data", "Any")]
LIST_ENV_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]


def _merge_params(params: dict[str, Any] | None) -> dict[str, Any]:
    return dict(params or {})


def _step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    p = _merge_params(params)
    root = repo_root_containing_units(Path(__file__))
    new_id = p.get("new_environment_id") or p.get("environment_id")
    readme = p.get("readme_md", "")
    if not new_id:
        return ({"data": None, "error": "missing param new_environment_id"}, state)
    result = run_list_environment(root, str(new_id), readme)
    if not result.get("ok"):
        err = result.get("error") or "list_environment failed"
        return ({"data": result, "error": str(err)}, state)
    return ({"data": result, "error": None}, state)


def register_list_environment() -> None:
    register_unit(UnitSpec(
        type_name="list_environment",
        input_ports=LIST_ENV_INPUT_PORTS,
        output_ports=LIST_ENV_OUTPUT_PORTS,
        step_fn=_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description=(
            "Create units/<tag>/ with README + register_env_loader; append import to units/env_loaders.py. "
            "Params: new_environment_id, readme_md (optional action: list_environment)."
        ),
    ))


__all__ = ["register_list_environment", "LIST_ENV_INPUT_PORTS", "LIST_ENV_OUTPUT_PORTS"]
