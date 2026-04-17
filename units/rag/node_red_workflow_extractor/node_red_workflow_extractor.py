from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

NODE_RED_WORKFLOW_EXTRACT_INPUT_PORTS = [("data", "Any"), ("file_path", "Any"), ("params", "Any")]
NODE_RED_WORKFLOW_EXTRACT_OUTPUT_PORTS = [("items", "Any"), ("error", "str")]


# -----------------------------
# Helpers (self-contained)
# -----------------------------

def _to_string(val: Any) -> str:
    """Normalize to string: keep str, convert list/dict to JSON string, else str()."""
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
    """Normalize to list of strings (e.g. keywords, categories)."""
    if val is None:
        return []
    if isinstance(val, list):
        return [_to_string(x) for x in val if x is not None]
    if isinstance(val, str):
        return [val] if val.strip() else []
    return [_to_string(val)]


def _extract_workflow_meta(raw: dict | list, source: str) -> dict[str, Any]:
    """Match extract_node_red_workflow_meta from extractors.py (Node-RED flow JSON)."""
    nodes: list[dict] = []
    if isinstance(raw, list):
        nodes = raw
    elif isinstance(raw, dict):
        nodes = raw.get("nodes") or raw.get("flow") or []
        if not nodes and raw.get("flows") and isinstance(raw["flows"], list) and raw["flows"]:
            first = raw["flows"][0]
            if isinstance(first, dict) and "nodes" in first:
                nodes = first["nodes"]
            elif isinstance(first, list):
                nodes = first

    unit_types: set[str] = set()
    labels: list[str] = []
    name = "Unknown"

    for n in nodes:
        if not isinstance(n, dict):
            continue
        ntype = (n.get("type") or n.get("unitType") or n.get("processType") or "")
        if str(ntype).lower() == "tab":
            name = _to_string(n.get("label") or n.get("name") or name)
        if ntype:
            unit_types.add(str(ntype).split(".")[-1])
        lbl = n.get("label") or n.get("name")
        if lbl is not None and str(ntype).lower() != "tab":
            labels.append(_to_string(lbl))

    if isinstance(raw, dict):
        if name == "Unknown":
            tab = raw.get("flows", [{}])[0] if raw.get("flows") else raw
            if isinstance(tab, dict):
                name = _to_string(tab.get("label") or tab.get("name") or name)
        summary = _to_string(raw.get("summary") or "")
        readme = _to_string(raw.get("readme") or "")
        if summary or readme:
            if name == "Unknown" and summary:
                name = summary[:200] if len(summary) <= 200 else summary[:197] + "..."
            elif name == "Unknown" and readme:
                name = readme[:80].strip() if len(readme) <= 80 else readme[:77].strip() + "..."
    else:
        summary = ""
        readme = ""

    result: dict[str, Any] = {
        "content_type": "workflow",
        "format": "node_red",
        "name": name,
        "source": source,
        "unit_types": list(unit_types),
        "labels": labels[:20],
        "node_count": len([n for n in nodes if isinstance(n, dict) and n.get("type")]),
    }
    if isinstance(raw, dict):
        if summary:
            result["summary"] = summary[:500]
        if readme:
            result["readme"] = readme[:2000]
    return result


def _to_text(meta: dict[str, Any]) -> str:
    """Match workflow_meta_to_text behavior from extractors.py."""
    parts = [f"Workflow: {meta.get('name', '')}"]
    if meta.get("origin"):
        parts.append(f"Origin: {meta['origin']}")
    if meta.get("description"):
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

def _node_red_workflow_extract_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
):
    try:
        raw = inputs.get("data")

        if not isinstance(raw, (dict, list)):
            return {"items": [], "error": "data must be a dict or list"}, state

        # normalization: allow raw list or dict
        graph = raw
        if isinstance(raw, dict):
            graph = raw.get("graph") or raw.get("parsed") or raw

        fp = str(raw.get("file_path") or "").strip() if isinstance(raw, dict) else ""
        fp_w = inputs.get("file_path")
        if isinstance(fp_w, str) and fp_w.strip():
            fp = fp_w.strip()

        path = Path(fp) if fp else Path(".")

        # If graph is not a dict (e.g., list) and a .json path exists, try to load it
        if not isinstance(graph, dict) and fp and path.suffix.lower() == ".json" and path.is_file():
            try:
                graph = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except Exception as e:
                return {"items": [], "error": str(e)}, state

        if not isinstance(graph, dict) and not isinstance(graph, list):
            return {"items": [], "error": "workflow must be a dict or list"}, state

        source = ""
        if isinstance(raw, dict):
            source = str(raw.get("source") or "").strip() or (Path(fp).name if fp else "")
        else:
            source = (Path(fp).name if fp else "")

        # extraction using aligned helper
        meta = _extract_workflow_meta(graph, source)

        # Add file/origin fields consistent with extractors.py callers
        meta["file_path"] = str(path)
        meta["raw_json_path"] = str(path)
        meta["origin"] = "node_red_workflow"

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

def register_node_red_workflow_extract() -> None:
    register_unit(
        UnitSpec(
            type_name="NodeRedWorkflowExtract",
            input_ports=NODE_RED_WORKFLOW_EXTRACT_INPUT_PORTS,
            output_ports=NODE_RED_WORKFLOW_EXTRACT_OUTPUT_PORTS,
            step_fn=_node_red_workflow_extract_step,
            environment_tags_are_agnostic=True,
            description="Node-RED workflow extractor aligned with extractors.py behavior.",
        )
    )
