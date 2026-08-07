from __future__ import annotations

from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

NEW_DIR_INPUT_PORTS = [("parser_output", "Any")]
NEW_DIR_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]


def _extract_dir_request(parser_output: Any) -> tuple[Path | None, Path | None]:
    """
    Accepts either:
    1) { "path": "/abs/or/rel/path" }
    2) { "action": "make_dir", "path": "/abs/or/rel/path" }  (wrapper supported)

    Returns (target_dir, base_dir) where base_dir is optional (unused here).
    """
    if isinstance(parser_output, list):
        parser_output = {}
    if not isinstance(parser_output, dict):
        return None, None

    # Wrapper support: { "action": "make_dir", "path": ... }
    if parser_output.get("action") == "make_dir":
        parser_output = dict(parser_output)  # shallow copy

    raw_path = parser_output.get("path")
    if raw_path is None:
        return None, None

    try:
        target_dir = Path(str(raw_path).strip()).expanduser().resolve()
    except (OSError, RuntimeError, ValueError, TypeError):
        return None, None

    return target_dir, None


def _make_dir_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    out: dict[str, Any] = {"ok": False, "output_path": "", "error": None}

    parser_output = inputs.get("parser_output")
    target_dir, _ = _extract_dir_request(parser_output)

    if not target_dir:
        out["error"] = "missing or invalid directory path (expected parser_output['path'])"
        return ({"data": out, "error": out["error"]}, state)

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        out["error"] = f"cannot create directory: {e}"
        return ({"data": out, "error": out["error"]}, state)

    out["ok"] = True
    out["output_path"] = str(target_dir)
    return ({"data": out, "error": None}, state)


def register_make_dir_unit() -> None:
    register_unit(
        UnitSpec(
            type_name="MakeDir",
            input_ports=NEW_DIR_INPUT_PORTS,
            output_ports=NEW_DIR_OUTPUT_PORTS,
            step_fn=_make_dir_step,
            environment_tags=["coding"],
            environment_tags_are_agnostic=False,
            description=(
                "Create a directory (recursively) given parser_output['path'] "
                "(supports optional wrapper: {action:'make_dir', path:...})."
            ),
        )
    )


__all__ = ["NEW_DIR_INPUT_PORTS", "NEW_DIR_OUTPUT_PORTS", "register_make_dir_unit"]
