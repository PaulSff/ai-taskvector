from __future__ import annotations

from pathlib import Path
from typing import cast

from units.registry import UnitSpec, register_unit

NEW_DIR_INPUT_PORTS = [("parser_output", "Any")]
NEW_DIR_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]


def _extract_dir_request(
    parser_output: object,
) -> tuple[Path | None, Path | None]:
    """
    Accepts either:
    1) {"path": "/abs/or/rel/path"}
    2) {"action": "make_dir", "path": "/abs/or/rel/path"}

    Returns (target_dir, base_dir), where base_dir is optional and unused here.
    """
    if isinstance(parser_output, list):
        parser_output = {}

    if not isinstance(parser_output, dict):
        return None, None

    payload = cast(dict[str, object], parser_output)

    # Wrapper support: {"action": "make_dir", "path": ...}
    if payload.get("action") == "make_dir":
        payload = dict(payload)

    raw_path = payload.get("path")
    if raw_path is None:
        return None, None

    try:
        target_dir = Path(str(raw_path).strip()).expanduser().resolve()
    except (OSError, RuntimeError, ValueError, TypeError):
        return None, None

    return target_dir, None


def _make_dir_step(
    params: dict[str, object],
    inputs: dict[str, object],
    state: dict[str, object],
    dt: float
) -> tuple[dict[str, object], dict[str, object]]:
    out: dict[str, object] = {"ok": False, "output_path": "", "error": None}

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
