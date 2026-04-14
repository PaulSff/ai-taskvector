"""
MydataOrganize unit: move root-level files under mydata into RAG layout (rag.mydata_file_manager_ops).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

from rag.mydata_file_manager_ops import organize_mydata_root

MYDATA_ORGANIZE_INPUT_PORTS: list[tuple[str, str]] = []
MYDATA_ORGANIZE_OUTPUT_PORTS = [("moved", "int"), ("error", "str")]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_under_repo(raw: str) -> Path:
    p = Path(raw.strip()).expanduser()
    if not p.is_absolute():
        p = _repo_root() / p
    return p.resolve()


def _mydata_organize_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = (params.get("mydata_dir") or "").strip()
    if not raw:
        return ({"moved": 0, "error": "mydata_dir is required"}, state)
    mydata = _resolve_under_repo(str(raw))
    try:
        n = organize_mydata_root(mydata)
    except Exception as e:
        return ({"moved": 0, "error": str(e)[:300]}, state)
    return ({"moved": int(n), "error": ""}, state)


def register_mydata_organize() -> None:
    register_unit(
        UnitSpec(
            type_name="MydataOrganize",
            input_ports=MYDATA_ORGANIZE_INPUT_PORTS,
            output_ports=MYDATA_ORGANIZE_OUTPUT_PORTS,
            step_fn=_mydata_organize_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description="Organize loose files under mydata root into node-red/, n8n/, canonical/, _organized/. Params: mydata_dir (settings.mydata_dir). Outputs: moved count, error.",
        )
    )


__all__ = [
    "register_mydata_organize",
    "MYDATA_ORGANIZE_INPUT_PORTS",
    "MYDATA_ORGANIZE_OUTPUT_PORTS",
]
