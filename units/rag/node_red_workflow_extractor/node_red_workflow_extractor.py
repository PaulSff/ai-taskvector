from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

NODE_RED_WORKFLOW_EXTRACT_INPUT_PORTS = [("data", "Any"), ("file_path", "Any")]
NODE_RED_WORKFLOW_EXTRACT_OUTPUT_PORTS = [("items", "Any"), ("error", "str")]

# Defaults (configurable via params)
DEFAULT_NAME_FALLBACK = "Unknown"
DEFAULT_LABEL_LIMIT = 20
DEFAULT_SUMMARY_LIMIT = 500
DEFAULT_README_LIMIT = 2000


# -----------------------------
# Helpers
# -----------------------------


def _to_string(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (list, dict)):
        try:
            return json.dumps(val, ensure_ascii=False)
        except Exception:
            return str(val)
    return str(val)


def _extract_workflow_meta(
    raw: dict | list,
    source: str,
    *,
    label_limit: int,
    summary_limit: int,
    readme_limit: int,
) -> dict[str, Any]:
    nodes: list[dict] = []

    if isinstance(raw, list):
        nodes = raw
    elif isinstance(raw, dict):
        nodes = raw.get("nodes") or raw.get("flow") or []

        if not nodes and raw.get("flows"):
            flows = raw["flows"]
            if isinstance(flows, list) and flows:
                first = flows[0]
                if isinstance(first, dict):
                    nodes = first.get("nodes", [])
                elif isinstance(first, list):
                    nodes = first

    unit_types: set[str] = set()
    labels: list[str] = []
    name = DEFAULT_NAME_FALLBACK
    typed_count = 0

    for n in nodes:
        if not isinstance(n, dict):
            continue

        ntype = str(n.get("type") or "")

        if not ntype:
            continue

        typed_count += 1

        if ntype.lower() == "tab":
            tab_name = _to_string(n.get("label") or n.get("name") or "")
            if tab_name:
                name = tab_name
        else:
            unit_types.add(ntype.split(".")[-1])
            lbl = n.get("label") or n.get("name")
            if lbl:
                labels.append(_to_string(lbl))

    # flows[0] label/name fallback when no tab node set the name
    if name == DEFAULT_NAME_FALLBACK and isinstance(raw, dict):
        flows = raw.get("flows")
        if isinstance(flows, list) and flows:
            first = flows[0]
            if isinstance(first, dict):
                fb = first.get("label") or first.get("name")
                if fb:
                    name = _to_string(fb)

    summary = ""
    readme = ""

    if isinstance(raw, dict):
        summary = _to_string(raw.get("summary") or "")[:summary_limit]
        readme = _to_string(raw.get("readme") or "")[:readme_limit]

    # Last-resort name fallback: use leading text from summary or readme
    if name == DEFAULT_NAME_FALLBACK:
        if summary:
            name = summary[:80].rstrip()
        elif readme:
            name = readme[:80].rstrip()

    return {
        "content_type": "workflow",
        "format": "node_red",
        "name": name,
        "source": source,
        "unit_types": list(unit_types),
        "labels": labels[:label_limit],
        "node_count": typed_count,
        "summary": summary,
        "readme": readme,
    }


def _to_text(meta: dict[str, Any]) -> str:
    parts = [f"Workflow: {meta.get('name', '')}"]

    if meta.get("origin"):
        parts.append(f"Origin: {meta['origin']}")

    if meta.get("unit_types"):
        parts.append(f"Node types: {', '.join(meta['unit_types'])}")

    if meta.get("labels"):
        parts.append(f"Nodes: {', '.join(meta['labels'][:10])}")

    if meta.get("summary"):
        parts.append(meta["summary"])

    if meta.get("readme"):
        parts.append(meta["readme"][:500])

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

        # Handle "parsed" / context bundle from router
        if isinstance(raw, dict) and "parsed" in raw:
            raw = raw["parsed"]

        # -------------------------
        # Resolve graph
        # -------------------------
        graph = None

        if isinstance(raw, dict):
            graph = raw.get("graph") or raw.get("parsed") or raw.get("flow") or raw
        elif isinstance(raw, list):
            graph = raw

        # -------------------------
        # Resolve file path
        # -------------------------
        fp = ""
        if isinstance(raw, dict):
            fp = str(raw.get("file_path") or "").strip()

        fp_input = inputs.get("file_path")
        if isinstance(fp_input, str) and fp_input.strip():
            fp = fp_input.strip()

        path = Path(fp) if fp else Path(".")

        # -------------------------
        # Load from disk fallback
        # -------------------------
        if not isinstance(graph, (dict, list)) and fp and path.is_file():
            try:
                graph = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                return {"items": [], "error": str(e)}, state

        if not isinstance(graph, (dict, list)):
            return {"items": [], "error": "Invalid workflow structure"}, state

        # -------------------------
        # Source
        # -------------------------
        source = ""
        if isinstance(raw, dict):
            source = str(raw.get("source") or "").strip()
        if not source and fp:
            source = Path(fp).name

        # -------------------------
        # Params
        # -------------------------
        label_limit = int(params.get("label_limit", DEFAULT_LABEL_LIMIT))
        summary_limit = int(params.get("summary_limit", DEFAULT_SUMMARY_LIMIT))
        readme_limit = int(params.get("readme_limit", DEFAULT_README_LIMIT))

        # -------------------------
        # Extract
        # -------------------------
        meta = _extract_workflow_meta(
            graph,
            source,
            label_limit=label_limit,
            summary_limit=summary_limit,
            readme_limit=readme_limit,
        )

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
            description="Self-contained Node-RED workflow extractor (aligned with extractors.py node-red behavior).",
        )
    )


__all__ = [
    "register_node_red_workflow_extract",
    "NODE_RED_WORKFLOW_EXTRACT_INPUT_PORTS",
    "NODE_RED_WORKFLOW_EXTRACT_OUTPUT_PORTS",
]
