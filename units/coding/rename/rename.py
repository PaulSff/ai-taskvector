from __future__ import annotations

from pathlib import Path
from typing import cast

from units.registry import UnitSpec, register_unit

RENAME_INPUT_PORTS = [("parser_output", "Any")]
RENAME_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]


def _extract_rename_request(
    parser_output: object,
) -> tuple[Path | None, str | None]:
    """
    Accepts either:
    1) {"path": "...", "new_name": "..."}
    2) {"action": "rename", "path": "...", "new_name": "..."}
    """
    if isinstance(parser_output, list):
        parser_output = {}

    if not isinstance(parser_output, dict):
        return None, None

    data = cast(dict[str, object], parser_output)

    raw_path = data.get("path")
    raw_new_name = data.get("new_name")

    if raw_path is None or raw_new_name is None:
        return None, None

    try:
        curr_path = Path(str(raw_path).strip()).expanduser().resolve()
    except (OSError, RuntimeError, ValueError, TypeError):
        return None, None

    if not isinstance(raw_new_name, str):
        return None, None

    new_name = raw_new_name.strip()
    if not new_name:
        return None, None

    # Strip directories; rename within the same parent directory.
    new_name = Path(new_name).name

    return curr_path, new_name


def _rename_step(
    params: dict[str, object],
    inputs: dict[str, object],
    state: dict[str, object],
    dt: float,
) -> tuple[dict[str, object], dict[str, object]]:
    out: dict[str, object] = {"ok": False, "output_path": "", "error": None}

    parser_output = inputs.get("parser_output")
    curr_path, new_name = _extract_rename_request(parser_output)

    if not curr_path or not new_name:
        out["error"] = "missing or invalid rename request (expected parser_output['path'] and parser_output['new_name'])"
        return ({"data": out, "error": out["error"]}, state)

    if not curr_path.exists() and not curr_path.is_symlink():
        out["error"] = f"path does not exist: {curr_path}"
        return ({"data": out, "error": out["error"]}, state)

    target_path = curr_path.with_name(new_name)

    try:
        if target_path.exists() or target_path.is_symlink():
            out["error"] = f"target already exists: {target_path}"
            return ({"data": out, "error": out["error"]}, state)

        renamed_path = curr_path.rename(target_path)

    except OSError as e:
        out["error"] = f"cannot rename: {e}"
        return ({"data": out, "error": out["error"]}, state)

    out["ok"] = True
    out["output_path"] = str(renamed_path)
    return ({"data": out, "error": None}, state)


def register_rename_unit() -> None:
    register_unit(
        UnitSpec(
            type_name="Rename",
            input_ports=RENAME_INPUT_PORTS,
            output_ports=RENAME_OUTPUT_PORTS,
            step_fn=_rename_step,
            environment_tags=["coding"],
            environment_tags_are_agnostic=False,
            description=(
                "Rename a file or folder in place given parser_output['path'] and parser_output['new_name']. "
                "Renames within the same parent directory (new_name only). "
                "Supports optional wrapper: {action:'rename', path:..., new_name:...}."
            ),
        )
    )


__all__ = ["RENAME_INPUT_PORTS", "RENAME_OUTPUT_PORTS", "register_rename_unit"]
