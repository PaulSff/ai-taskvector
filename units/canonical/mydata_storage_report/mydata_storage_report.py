"""
MydataStorageReport unit: directory listing + storage summary + pie chart payload for mydata browser.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

from rag.mydata_file_manager_ops import build_mydata_refresh_view_model

# organize_moved is wired from MydataOrganize so this unit runs after organize (value unused).
MYDATA_STORAGE_REPORT_INPUT_PORTS = [("organize_moved", "int"), ("rel_parts", "Any")]
MYDATA_STORAGE_REPORT_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_under_repo(raw: str) -> Path:
    p = Path(raw.strip()).expanduser()
    if not p.is_absolute():
        p = _repo_root() / p
    return p.resolve()


def _coerce_rel_parts(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip() and str(x) != "."]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def _mydata_storage_report_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_dir = (params.get("mydata_dir") or "").strip()
    if not raw_dir:
        return ({"data": {}, "error": "mydata_dir is required"}, state)
    mydata = _resolve_under_repo(str(raw_dir))
    rel_parts = _coerce_rel_parts(inputs.get("rel_parts") if inputs else None)
    try:
        payload = build_mydata_refresh_view_model(mydata, rel_parts)
    except Exception as e:
        return ({"data": {}, "error": str(e)[:300]}, state)
    return ({"data": payload, "error": ""}, state)


def register_mydata_storage_report() -> None:
    register_unit(
        UnitSpec(
            type_name="MydataStorageReport",
            input_ports=MYDATA_STORAGE_REPORT_INPUT_PORTS,
            output_ports=MYDATA_STORAGE_REPORT_OUTPUT_PORTS,
            step_fn=_mydata_storage_report_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description="Mydata browser payload: entries for one folder level, summary_text, pie_src, rel_parts_effective. Params: mydata_dir. Inputs: rel_parts; organize_moved (int, from MydataOrganize or 0 when using report-only workflow).",
        )
    )


__all__ = [
    "register_mydata_storage_report",
    "MYDATA_STORAGE_REPORT_INPUT_PORTS",
    "MYDATA_STORAGE_REPORT_OUTPUT_PORTS",
]
