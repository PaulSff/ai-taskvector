from __future__ import annotations

from pathlib import Path
from typing import cast

from units.registry import UnitSpec, register_unit

DELETE_INPUT_PORTS = [("parser_output", "Any")]
DELETE_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]


def _extract_delete_request(parser_output: object) -> Path | None:
    """
    Accepts either:

    1. {"path": "/abs/or/rel/path"}
    2. {"action": "delete", "path": "/abs/or/rel/path"}
    """
    if isinstance(parser_output, list):
        parser_output = {}

    if not isinstance(parser_output, dict):
        return None

    typed_parser_output = cast(
        dict[str, object],
        cast(object, parser_output),
    )

    raw_path = typed_parser_output.get("path")
    if raw_path is None:
        return None

    try:
        return Path(str(raw_path).strip()).expanduser().resolve()
    except (OSError, RuntimeError, ValueError, TypeError):
        return None


def _delete_step(
    inputs: dict[str, object],
    state: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    out: dict[str, object] = {"ok": False, "deleted_path": "", "error": None}

    parser_output = inputs.get("parser_output")
    target_path = _extract_delete_request(parser_output)

    if not target_path:
        out["error"] = "missing or invalid path (expected parser_output['path'])"
        return ({"data": out, "error": out["error"]}, state)

    if not target_path.exists() and not target_path.is_symlink():
        out["error"] = f"path does not exist: {target_path}"
        return ({"data": out, "error": out["error"]}, state)

    try:
        if target_path.is_dir() and not target_path.is_symlink():
            # Recursively delete directory contents
            for p in sorted(target_path.rglob("*"), reverse=True):
                if p.is_dir() and not p.is_symlink():
                    p.rmdir()
                else:
                    p.unlink()
            target_path.rmdir()
        else:
            # Delete file or symlink
            target_path.unlink()
    except OSError as e:
        out["error"] = f"cannot delete path: {e}"
        return ({"data": out, "error": out["error"]}, state)

    out["ok"] = True
    out["deleted_path"] = str(target_path)
    return ({"data": out, "error": None}, state)


def register_delete_unit() -> None:
    register_unit(
        UnitSpec(
            type_name="Delete",
            input_ports=DELETE_INPUT_PORTS,
            output_ports=DELETE_OUTPUT_PORTS,
            step_fn=_delete_step,
            environment_tags=["coding"],
            environment_tags_are_agnostic=False,
            description=(
                "Delete either a file, symlink, or directory (recursively) given parser_output['path']. "
                "Supports optional wrapper: {action:'delete', path:...}."
            ),
        )
    )


__all__ = ["DELETE_INPUT_PORTS", "DELETE_OUTPUT_PORTS", "register_delete_unit"]
