"""
RagExtract unit: build a flat dict from ``params.paths`` (dot paths and optional constants).

Each path item: ``{"out": "key", "from": "nested.path"}`` or ``{"out": "key", "constant": <any>}``.
``from`` walks dict keys only (missing → null). Values are JSON-serializable when possible.
"""
from __future__ import annotations

import json
from typing import Any

from units.registry import UnitSpec, register_unit

RAG_EXTRACT_INPUT_PORTS = [("data", "Any")]
RAG_EXTRACT_OUTPUT_PORTS = [("extracted", "Any"), ("error", "str")]


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
    out: dict[str, Any] = {}
    for item in paths:
        if not isinstance(item, dict):
            continue
        key = str(item.get("out") or item.get("key") or "").strip()
        if not key:
            continue
        if "constant" in item:
            out[key] = _jsonable(item.get("constant"))
            continue
        frm = str(item.get("from") or item.get("path") or "").strip()
        if not frm:
            continue
        out[key] = _jsonable(_get_path(data, frm))

    return {"extracted": out, "error": err}, state


def register_rag_extract() -> None:
    register_unit(
        UnitSpec(
            type_name="RagExtract",
            input_ports=RAG_EXTRACT_INPUT_PORTS,
            output_ports=RAG_EXTRACT_OUTPUT_PORTS,
            step_fn=_rag_extract_step,
            environment_tags_are_agnostic=True,
            description="Params.paths: [{out, from} | {out, constant}]. Dot paths on dict input only.",
        )
    )


__all__ = ["register_rag_extract", "RAG_EXTRACT_INPUT_PORTS", "RAG_EXTRACT_OUTPUT_PORTS"]
