from __future__ import annotations

from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

LIST_DIR_INPUT_PORTS = [
    (
        "action",
        "Any",  # must contain {"action":"list_dir","path":"<local_path>"}
    ),
    (
        "path",
        "str",  # path to local directory
    ),
]

LIST_DIR_OUTPUT_PORTS = [
    ("data", "Any"),  # list[str] of file names (non-recursive)
    ("error", "str"),  # error message or None
]


def _extract_expected_action_path(action_port: Any) -> str | None:
    if not isinstance(action_port, dict):
        return None
    if action_port.get("action") != "list_dir":
        return None
    if "path" not in action_port or action_port.get("path") is None:
        return None
    return str(action_port.get("path"))


def _list_dir_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    err_msg: str | None = None
    data: list[str] = []

    try:
        action_port = inputs.get("action")
        expected_path_from_action = _extract_expected_action_path(action_port)

        path_port = inputs.get("path")
        if path_port is None:
            raise ValueError("missing input port 'path'")

        path_str = str(path_port).strip()
        if not path_str:
            raise ValueError("empty input 'path'")

        # Enforce "exact payload" semantics: action must match and include path.
        if expected_path_from_action is None:
            raise ValueError(
                "input 'action' must be exactly {'action': 'list_dir', 'path': '<local_path>'}"
            )
        if expected_path_from_action != path_str:
            raise ValueError(
                "input 'action.path' must exactly match input 'path'"
            )

        p = Path(path_str).expanduser()

        if not p.exists():
            raise FileNotFoundError(f"path not found: {path_str}")
        if not p.is_dir():
            raise NotADirectoryError(f"not a directory: {path_str}")

        # Deterministic order; list files only (non-recursive)
        entries = sorted(p.iterdir(), key=lambda x: x.name.lower())
        data = [e.name for e in entries if e.is_file()]
    except (FileNotFoundError, NotADirectoryError, ValueError) as e:
        err_msg = str(e)[:400]
        data = []
    except OSError as e:
        # Covers permission errors, I/O failures, etc.
        err_msg = str(e)[:400]
        data = []

    return ({"data": data, "error": err_msg}, state)


def register_list_dir() -> None:
    register_unit(
        UnitSpec(
            type_name="ListDir",
            input_ports=LIST_DIR_INPUT_PORTS,
            output_ports=LIST_DIR_OUTPUT_PORTS,
            step_fn=_list_dir_step,
            environment_tags=["discovery"],
            environment_tags_are_agnostic=False,
            description=(
                "List files (non-recursive) in a local directory. "
                "Inputs: 'action' must be {'action':'list_dir','path':'<local_path>'} and "
                "'path' must be the same '<local_path>'. "
                "Outputs: data (list of file names), error (string or None)."
            ),
        )
    )


__all__ = ["LIST_DIR_INPUT_PORTS", "LIST_DIR_OUTPUT_PORTS", "register_list_dir"]
