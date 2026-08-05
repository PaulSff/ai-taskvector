from __future__ import annotations

from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

# Use the same port-spec style as in your grep unit:
# list of (port_name, port_type_as_string_or_any)
LIST_DIR_INPUT_PORTS = [
    ("action", "Any"),  # payload: {"action":"list_dir","path":"<local_path>"}
    ("path", "Any"),    # optional/ignored if runner only provides action payload
    ("data", "Any"),    # optional/ignored if runner only provides action payload
]

LIST_DIR_OUTPUT_PORTS = [
    ("data", "Any"),   # {"path": str, "content": {"dirs": list[str], "files": list[str]}}
    ("error", "str"),  # error message or None
]

def _validate_action_payload(action_port: Any) -> str:
    if not isinstance(action_port, dict):
        raise TypeError("input 'action' must be a dict")

    if action_port.get("action") != "list_dir":
        raise ValueError("input 'action.action' must be 'list_dir'")

    if action_port.get("path") is None:
        raise ValueError("input 'action.path' is required")

    action_path_str = str(action_port.get("path")).strip()
    if not action_path_str:
        raise ValueError("input 'action.path' is empty")

    return action_path_str


def _list_dir_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:

    err_msg: str | None = None
    data: dict[str, Any] = {"path": "", "content": {"dirs": [], "files": []}}

    try:
        action_payload = inputs.get("action")
        if action_payload is None and isinstance(inputs.get("data"), dict):
            action_payload = inputs["data"]
        if action_payload is None:
            raise ValueError("missing payload: provide inputs['action'] (or inputs['data'])")

        path_str = _validate_action_payload(action_payload)

        if inputs.get("path") is not None:
            path_port_str = str(inputs["path"]).strip()
            if path_port_str != path_str:
                raise ValueError("input 'path' must exactly match payload 'action.path'")

        p = Path(path_str).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"path not found: {path_str}")

        # Always include the path in the output
        data["path"] = str(p)

        # If the provided path is a file, return it under files
        if p.is_file():
            data["content"] = {"dirs": [], "files": [p.name]}
            return ({"data": data, "error": err_msg}, state)

        # If it's a directory, return both subdirs and files
        if not p.is_dir():
            raise ValueError(f"unsupported path type (not file or directory): {path_str}")

        entries = sorted(p.iterdir(), key=lambda x: x.name.lower())
        data["content"] = {
            "dirs": [e.name for e in entries if e.is_dir()],
            "files": [e.name for e in entries if e.is_file()],
        }

    except (FileNotFoundError, ValueError, TypeError, OSError) as e:
        err_msg = str(e)[:400]
        data = {"path": "", "content": {"dirs": [], "files": []}}

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
                "Expects payload in inputs['action']: {'action':'list_dir','path':'<local_path>'}. "
                "Optional: if inputs['path'] is present, it must exactly match action.path. "
                "Outputs: data (list of file names), error (string or None)."
            ),
        )
    )


__all__ = ["LIST_DIR_INPUT_PORTS", "LIST_DIR_OUTPUT_PORTS", "register_list_dir"]
