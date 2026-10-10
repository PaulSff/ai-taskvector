from __future__ import annotations

import json
from pathlib import Path
from typing import TypeGuard

from core.schemas.primitives import Data, JsonObject, is_data, safe_int
from units.registry import UnitSpec, register_unit

RAG_CANONICAL_WORKFLOW_EXTRACT_INPUT_PORTS = [("data", "JsonObject"), ("file_path", "str")]
RAG_CANONICAL_WORKFLOW_EXTRACT_OUTPUT_PORTS = [("items", "JsonArray"), ("error", "str")]


# Defaults (configurable via params)
DEFAULT_NAME_FALLBACK = "Canonical graph"
DEFAULT_LABEL_LIMIT = 20
DEFAULT_DESC_LIMIT = 4000


# -----------------------------
# Helpers (self-contained)
# -----------------------------


def _to_string(val: object) -> str:
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


def is_data_list(value: object) -> TypeGuard[list[Data]]:
    return isinstance(value, list) and all(is_data(item) for item in value)


def _extract_units(raw: JsonObject) -> list[Data]:
    units = raw.get("units")
    if not is_data_list(units):
        return []
    return units


def _extract_meta(
    raw: JsonObject, source: str, *, label_limit: int, desc_limit: int
) -> Data:
    units = _extract_units(raw)

    unit_types: set[str] = set()
    labels: list[str] = []

    for u in units:
        if not isinstance(u, dict):
            continue

        utype_val = u.get("type")
        if isinstance(utype_val, str):
            utype = utype_val.strip()
            if utype:
                unit_types.add(utype)

        uid = u.get("id")
        if uid is not None:
            labels.append(_to_string(uid))

    name = _to_string(raw.get("name") or DEFAULT_NAME_FALLBACK)

    desc = _to_string(raw.get("description") or "")
    metadata = raw.get("metadata")
    if not desc.strip() and isinstance(metadata, dict):
        desc = _to_string(metadata.get("description") or "")

    result: Data = {
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


def _to_text(meta: Data) -> str:
    parts = [
        f"Workflow: {meta.get('name', '')}",
    ]

    if meta.get("origin"):
        parts.append(f"Origin: {meta['origin']}")

    if meta.get("description"):
        parts.append(_to_string(meta.get("description"))[:2000])

    unit_types = meta.get("unit_types")
    if isinstance(unit_types, list):
        parts.append(f"Node types: {', '.join(str(x) for x in unit_types)}")

    integrations = meta.get("integrations")
    if isinstance(integrations, list):
        parts.append(f"Integrations: {', '.join(str(x) for x in integrations)}")

    labels = meta.get("labels")
    if isinstance(labels, list):
        parts.append(f"Nodes: {', '.join(str(x) for x in labels[:10])}")

    if meta.get("summary"):
        parts.append(str(meta.get("summary", "")))

    if meta.get("readme"):
        parts.append(str(meta.get("readme") or "")[:500])

    parts.append(f"Format: {meta.get('format', '')}")

    return " | ".join(p for p in parts if p)

# -----------------------------
# Step
# -----------------------------

def _canonical_extract_step(
    params: Data,
    inputs: Data,
    state: Data,
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

        if (
            not isinstance(graph, dict)
            and fp
            and path.suffix.lower() == ".json"
            and path.is_file()
        ):
            try:
                graph = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except (FileNotFoundError, PermissionError, IsADirectoryError) as e:
                return {"items": [], "error": str(e)}, state
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                return {"items": [], "error": str(e)}, state


        if not isinstance(graph, dict):
            return {"items": [], "error": "canonical workflow must be a dict"}, state

        source = str(raw.get("source") or "").strip() or (Path(fp).name if fp else "")

        # -----------------------------
        # params
        # -----------------------------
        label_limit_val = safe_int(params.get("label_limit"))
        desc_limit_val = safe_int(params.get("desc_limit"))

        label_limit = label_limit_val if label_limit_val is not None else DEFAULT_LABEL_LIMIT
        desc_limit = desc_limit_val if desc_limit_val is not None else DEFAULT_DESC_LIMIT

        # -----------------------------
        # extraction
        # -----------------------------
        meta = _extract_meta(
            graph, source, label_limit=label_limit, desc_limit=desc_limit
        )
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

    except (FileNotFoundError, PermissionError, IsADirectoryError) as e:
        return {"items": [], "error": str(e)}, state
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as e:
        return {"items": [], "error": str(e)}, state
    except (KeyError, AttributeError) as e:
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
            environment_tags=["rag"],
            environment_tags_are_agnostic=False,
            description="Self-contained canonical workflow extractor (aligned with extractors.py canonical behavior).",
        )
    )


__all__ = [
    "RAG_CANONICAL_WORKFLOW_EXTRACT_INPUT_PORTS",
    "RAG_CANONICAL_WORKFLOW_EXTRACT_OUTPUT_PORTS",
    "register_canonical_workflow_extract",
]
