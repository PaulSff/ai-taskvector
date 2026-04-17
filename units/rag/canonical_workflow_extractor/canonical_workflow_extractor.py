from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit


RAG_CANONICAL_WORKFLOW_EXTRACT_INPUT_PORTS = [("data", "Any"), ("file_path", "Any")]
RAG_CANONICAL_WORKFLOW_EXTRACT_OUTPUT_PORTS = [("items", "Any"), ("error", "str")]


# Defaults (configurable via params)
DEFAULT_NAME_FALLBACK = "Canonical graph"
DEFAULT_LABEL_LIMIT = 20
DEFAULT_DESC_LIMIT = 4000


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


def _extract_units(raw: dict) -> list[dict[str, Any]]:
    units = raw.get("units") or []
    return [u for u in units if isinstance(u, dict)]


def _extract_meta(raw: dict, source: str, *, label_limit: int, desc_limit: int) -> dict[str, Any]:
    units = _extract_units(raw)

    unit_types: set[str] = set()
    labels: list[str] = []

    for u in units:
        if not isinstance(u, dict):
            continue
        utype = (u.get("type") or "").strip()
        if utype:
            unit_types.add(utype)

        uid = u.get("id")
        if uid is not None:
            labels.append(_to_string(uid))

    name = _to_string(raw.get("name") or DEFAULT_NAME_FALLBACK)

    desc = _to_string(raw.get("description") or "")
    if not desc.strip() and isinstance(raw.get("metadata"), dict):
        desc = _to_string(raw["metadata"].get("description") or "")

    result: dict[str, Any] = {
        "content_type": "workflow",
        "format": "canonical",
        "name": name,
        "source": source,
        "unit_types": list(unit_types),
        "labels": labels[:label_limit],
        "node_count": len(units),
    }
    if desc.strip():
        result["description"] = desc.strip()[:desc_limit]
    return result


def _to_text(meta: dict[str, Any]) -> str:
    parts = [
        f"Workflow: {meta.get('name', '')}",
    ]

    if meta.get("origin"):
        parts.append(f"Origin: {meta['origin']}")

    if meta.get("description"):
        # follow extractors.py behavior: truncate description for text to 2000 chars
        parts.append(_to_string(meta.get("description"))[:2000])

    if meta.get("unit_types"):
        parts.append(f"Node types: {', '.join(meta['unit_types'])}")

    if meta.get("integrations"):
        parts.append(f"Integrations: {', '.join(meta['integrations'])}")

    if meta.get("labels"):
        parts.append(f"Nodes: {', '.join(meta['labels'][:10])}")

    if meta.get("summary"):
        parts.append(meta.get("summary", ""))

    if meta.get("readme"):
        parts.append((meta.get("readme") or "")[:500])

    parts.append(f"Format: {meta.get('format', '')}")

    return " | ".join(p for p in parts if p)


# -----------------------------
# Step
# -----------------------------

def _canonical_extract_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
):
    try:
        raw = inputs.get("data")

        if not isinstance(raw, dict):
            return {"items": [], "error": "canonical workflow must be a dict"}, state

        # -----------------------------
        # normalization (no external helpers)
        # -----------------------------
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
            return {"items": [], "error": "canonical workflow must be a dict"}, state

        source = str(raw.get("source") or "").strip() or (Path(fp).name if fp else "")

        # -----------------------------
        # params
        # -----------------------------
        label_limit = int(params.get("label_limit", DEFAULT_LABEL_LIMIT))
        desc_limit = int(params.get("desc_limit", DEFAULT_DESC_LIMIT))

        # -----------------------------
        # extraction
        # -----------------------------
        meta = _extract_meta(graph, source, label_limit=label_limit, desc_limit=desc_limit)
        meta["file_path"] = str(path)
        meta["raw_json_path"] = str(path)
        meta["origin"] = "canonical"

        # include summary/readme if present on wrapper (match extractors.py behavior)
        if isinstance(graph, dict):
            if graph.get("summary"):
                meta["summary"] = _to_string(graph.get("summary"))[:500]
            if graph.get("readme"):
                meta["readme"] = _to_string(graph.get("readme"))[:2000]

        text = _to_text(meta)

        # -----------------------------
        # output (NO chunking)
        # -----------------------------
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

def register_canonical_workflow_extract() -> None:
    register_unit(
        UnitSpec(
            type_name="CanonicalWorkflowExtract",
            input_ports=RAG_CANONICAL_WORKFLOW_EXTRACT_INPUT_PORTS,
            output_ports=RAG_CANONICAL_WORKFLOW_EXTRACT_OUTPUT_PORTS,
            step_fn=_canonical_extract_step,
            environment_tags_are_agnostic=True,
            description="Self-contained canonical workflow extractor (aligned with extractors.py canonical behavior).",
        )
    )

    __all__ = [
    "register_canonical_workflow_extract",
    "RAG_CANONICAL_WORKFLOW_EXTRACT_INPUT_PORTS",
    "RAG_CANONICAL_WORKFLOW_EXTRACT_OUTPUT_PORTS",
]
