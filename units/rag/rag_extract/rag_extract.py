""" RagExtract unit: build a list of flat dicts from ``params.paths`` (dot paths and optional constants).
Each path item: ``{"out": "key", "from": "nested.path"}`` or ``{"out": "key", "constant": <any>}``.
``from`` walks dict keys only (missing → null). Values are JSON-serializable when possible.
If input data is a list, extraction is applied to each element.
"""
from __future__ import annotations
import json
from typing import Any
from units.registry import UnitSpec, register_unit

RAG_EXTRACT_INPUT_PORTS = [("data", "Any")]
RAG_EXTRACT_OUTPUT_PORTS = [("items", "Any"), ("error", "str")]

def _get_path(obj: Any, path: str) -> Any:
    cur: Any = obj
    for part in str(path or "").strip().split("."):
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur

def _jsonable(val: Any) -> Any:
    if val is None or isinstance(val, (str, int, float, bool)):
        return val
    try:
        json.dumps(val)
        return val
    except (TypeError, ValueError):
        return str(val)

def _extract_single_item(item_data: Any, paths: list[dict[str, Any]]) -> dict[str, Any]:
    """Helper to extract paths from a single data object."""
    out: dict[str, Any] = {}
    for path_cfg in paths:
        if not isinstance(path_cfg, dict):
            continue
        key = str(path_cfg.get("out") or path_cfg.get("key") or "").strip()
        if not key:
            continue
        if "constant" in path_cfg:
            out[key] = _jsonable(path_cfg.get("constant"))
            continue
        frm = str(path_cfg.get("from") or path_cfg.get("path") or "").strip()
        if not frm:
            continue
        out[key] = _jsonable(_get_path(item_data, frm))
    return out

def _rag_extract_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    data = inputs.get("data")
    err = ""
    paths = params.get("paths")
    if not isinstance(paths, list):
        paths = []

    # Handle list of inputs vs single input
    if isinstance(data, list):
        items = [_extract_single_item(d, paths) for d in data]
    elif data is not None:
        items = [_extract_single_item(data, paths)]
    else:
        items = []

    return {"items": items, "error": err}, state

def register_rag_extract() -> None:
    register_unit(
        UnitSpec(
            type_name="RagExtract",
            input_ports=RAG_EXTRACT_INPUT_PORTS,
            output_ports=RAG_EXTRACT_OUTPUT_PORTS,
            step_fn=_rag_extract_step,
            environment_tags_are_agnostic=True,
            description="Params.paths: [{out, from} | {out, constant}]. Dot paths on dict input only. Outputs a list of extracted items.",
        )
    )

__all__ = ["register_rag_extract", "RAG_EXTRACT_INPUT_PORTS", "RAG_EXTRACT_OUTPUT_PORTS"]
