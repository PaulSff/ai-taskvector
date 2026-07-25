from __future__ import annotations

import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

INPUT_PORTS = [("data", "Any")]
OUTPUT_PORTS = [("data", "Any"), ("error", "str")]

DEFAULT_CLONE_SCRIPT_PATH = Path("agents/roles/clone_role.py")


def _get_str(d: dict[str, Any], key: str) -> str:
    v = d.get(key)
    return "" if v is None else str(v).strip()


def _coerce_tools(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        parts = [p.strip() for p in v.split(",")]
        return [p for p in parts if p]
    return [str(v).strip()]


def _get_clone_script_path(params: dict[str, Any]) -> Path:
    """
    Unit param override:
      clone_script_path (optional, str)
    Default:
      agents/roles/clone_role.py
    """
    raw = params.get("clone_script_path")
    if raw is None or str(raw).strip() == "":
        return DEFAULT_CLONE_SCRIPT_PATH
    return Path(str(raw).strip())


def _clone_role_via_script(
    payload: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    clone_script_path = _get_clone_script_path(params)
    if not clone_script_path.exists():
        return {"success": False, "error": f"Missing clone script: {clone_script_path}"}

    action = _get_str(payload, "action").lower()
    if action != "clone_role":
        return {"success": False, "error": f"Unsupported action: {action!r}"}

    new_role = _get_str(payload, "new_role_name").replace("-", "_")
    character_name = _get_str(payload, "character_name")

    responsibility = _get_str(payload, "responsibility")
    intro_brief = _get_str(payload, "intro_brief")
    prompt_duties = _get_str(payload, "prompt_duties")
    prompt_conversational_behavior = _get_str(payload, "prompt_conversational_behavior")
    prompt_reasoning = _get_str(payload, "prompt_reasoning")
    tools = _coerce_tools(payload.get("tools"))

    cmd = [
        sys.executable,
        str(clone_script_path),
        "--new-role",
        new_role,
        "--character-name",
        character_name,
        "--responsibility",
        responsibility,
        "--intro",
        intro_brief,
        "--intro-body",
        prompt_duties,
        "--conversational-behaviour",
        prompt_conversational_behavior,
        "--reasoning",
        prompt_reasoning,
    ]
    if tools:
        cmd += ["--tools", *tools]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    if proc.returncode != 0:
        return {
            "success": False,
            "error": stderr or stdout or f"clone_role.py failed with code {proc.returncode}",
            "stdout": stdout[:20000],
            "stderr": stderr[:20000],
            "returncode": proc.returncode,
        }

    return {
        "success": True,
        "new_role": new_role,
        "config_path": f"agents/roles/{new_role}/role.yaml",
        "workflow_path": f"agents/roles/{new_role}/{new_role}_workflow.json",
        "prompt_script_path": f"agents/roles/{new_role}/prompts.py",
        "tools": tools,
        "script_stdout": stdout[:20000],
    }


def _clone_role_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:

    from gui.components.settings import get_contribution_is_allowed

    data = inputs.get("data")

    try:
        # check if contribution is allowed from settings
        if not get_contribution_is_allowed():
            return (
                {"data": None, "error": "Operation is not permitted. Enable contribution in settings."},
                state,
            )

        if not isinstance(data, dict):
            return ({"data": None, "error": "Input 'data' must be an object"}, state)

        result = _clone_role_via_script(data, params)
        if not result.get("success"):
            return ({"data": None, "error": result.get("error", "clone_role failed")}, state)

        payload = {
            "success": True,
            "new_role": result["new_role"],
            "config_path": result["config_path"],
            "workflow_path": result["workflow_path"],
            "prompt_script_path": result["prompt_script_path"],
            "tools": result.get("tools", []),
        }
        return ({"data": payload, "error": ""}, state)

    except (subprocess.SubprocessError, OSError, ValueError):
        err = traceback.format_exc()
        return ({"data": None, "error": err[:2000]}, state)


def register_clone_role_unit() -> None:
    register_unit(
        UnitSpec(
            type_name="CloneRole",
            input_ports=INPUT_PORTS,
            output_ports=OUTPUT_PORTS,
            step_fn=_clone_role_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description="Clone a new role by calling agents/roles/clone_role.py. Input is a single data object; outputs success payload on data and error string on failure.",
        )
    )


__all__ = ["INPUT_PORTS", "OUTPUT_PORTS", "register_clone_role_unit"]
