from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

NODE_RED_CATALOGUE_EXTRACT_INPUT_PORTS = [("data", "Any"), ("file_path", "Any"), ("params", "Any")]
NODE_RED_CATALOGUE_EXTRACT_OUTPUT_PORTS = [("items", "Any"), ("error", "str")]

# -----------------------------
# Helpers (self-contained)
# -----------------------------

def _to_string(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (list, dict)):
        try:
            return json.dumps(val, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(val)
    return str(val)

def _to_string_list(val: Any) -> list[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [_to_string(x) for x in val if x is not None]
    if isinstance(val, str):
        return [val] if val.strip() else []
    return [_to_string(val)]

def _extract_catalogue_meta(module: dict, source: str) -> dict[str, Any]:
    mid = _to_string(module.get("id") or "")
    desc = _to_string(module.get("description") or "")
    keywords = _to_string_list(module.get("keywords"))
    types_list = _to_string_list(module.get("types"))[:30]
    categories = _to_string_list(module.get("categories"))
    url = _to_string(module.get("url") or "")

    return {
        "content_type": "node",
        "format": "node_red",
        "id": mid,
        "name": mid,
        "source": source,
        "description": desc,
        "keywords": keywords,
        "node_types": types_list,
        "categories": categories,
        "url": url,
    }

def _to_text(meta: dict[str, Any]) -> str:
    parts = [
        meta.get("name", ""),
        meta.get("description", ""),
        " ".join(meta.get("keywords", [])),
        " ".join(meta.get("categories", [])),
        " ".join(meta.get("node_types", [])[:15]),
    ]
    return " | ".join(p for p in parts if p)

# -----------------------------
# Step
# -----------------------------

def _node_red_catalogue_extract_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
):
    try:
        raw = inputs.get("data")

        if not isinstance(raw, dict):
            return {"items": [], "error": "catalogue module must be a dict"}, state

        # normalization (allow wrapper shapes and optional file loading)
        graph = raw.get("graph") or raw.get("parsed") or raw

        fp = str(raw.get("file_path") or "").strip()

        fp_w = inputs.get("file_path")
        if isinstance(fp_w, str) and fp_w.strip():
            fp = fp_w.strip()

        path = Path(fp) if fp else Path(".")

        if not isinstance(graph, dict) and fp and path.suffix.lower() == ".json" and path.is_file():
            try:
                graph = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except Exception as e:
                return {"items": [], "error": str(e)}, state

        if not isinstance(graph, dict):
            return {"items": [], "error": "catalogue module must be a dict"}, state

        source = str(raw.get("source") or "").strip() or (Path(fp).name if fp else "")

        meta = _extract_catalogue_meta(graph, source)

        meta["file_path"] = str(path)
        meta["raw_json_path"] = str(path)
        meta["origin"] = "node_red_catalogue"

        text = _to_text(meta)

        return {
            "items": [
                {
                    "text": text,
                    "metadata": meta,
                }
            ],
            "error": "",
        }, state

    except Exception as e:
        return {"items": [], "error": str(e)}, state

# -----------------------------
# Registration
# -----------------------------

def register_node_red_catalogue_extract() -> None:
    register_unit(
        UnitSpec(
            type_name="NodeRedCatalogueExtract",
            input_ports=NODE_RED_CATALOGUE_EXTRACT_INPUT_PORTS,
            output_ports=NODE_RED_CATALOGUE_EXTRACT_OUTPUT_PORTS,
            step_fn=_node_red_catalogue_extract_step,
            environment_tags_are_agnostic=True,
            description="Node-RED catalogue extractor aligned with extractors.py behavior.",
        )
    )
