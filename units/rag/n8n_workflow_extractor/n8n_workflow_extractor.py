from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

N8N_WORKFLOW_EXTRACTOR_INPUT_PORTS = [("data", "Any"), ("file_path", "Any")]
N8N_WORKFLOW_EXTRACTOR_OUTPUT_PORTS = [("items", "Any"), ("error", "str")]


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


def _extract_n8n_meta(raw: dict, source: str) -> dict[str, Any]:
    nodes = raw.get("nodes") or []

    integrations: set[str] = set()
    labels: list[str] = []

    for n in nodes:
        if not isinstance(n, dict):
            continue

        ntype = n.get("type") or ""
        if isinstance(ntype, str) and "." in ntype:
            integrations.add(ntype.split(".")[-1])

        name = n.get("name")
        if name is not None:
            labels.append(_to_string(name))

    wf_name = _to_string(
        raw.get("name")
        or (isinstance(raw.get("meta"), dict) and raw["meta"].get("instanceId"))
        or "Unknown"
    )

    return {
        "content_type": "workflow",
        "format": "n8n",
        "name": wf_name,
        "source": source,
        "integrations": list(integrations),
        "labels": labels[:20],
        "node_count": len(nodes),
    }


def _to_text(meta: dict[str, Any]) -> str:
    parts = [f"Workflow: {meta.get('name', '')}"]

    if meta.get("integrations"):
        parts.append(f"Integrations: {', '.join(meta['integrations'])}")

    if meta.get("labels"):
        parts.append(f"Nodes: {', '.join(meta['labels'][:10])}")

    parts.append(f"Format: {meta.get('format', '')}")

    return " | ".join(p for p in parts if p)


# -----------------------------
# Step
# -----------------------------


def _n8n_workflow_extract_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
):
    try:
        raw = inputs.get("data")

        if not isinstance(raw, dict):
            return {"items": [], "error": "data must be a dict"}, state

        # -----------------------------
        # normalization (self-contained)
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
            except Exception as e:
                return {"items": [], "error": str(e)}, state

        if not isinstance(graph, dict):
            return {"items": [], "error": "n8n workflow must be a dict"}, state

        source = str(raw.get("source") or "").strip() or (Path(fp).name if fp else "")

        # -----------------------------
        # extraction
        # -----------------------------
        meta = _extract_n8n_meta(graph, source)

        # Add file/origin fields consistent with the Node-RED unit pattern
        meta["file_path"] = str(path)
        meta["raw_json_path"] = str(path)
        meta["origin"] = "n8n_workflow"

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


def register_n8n_workflow_extract() -> None:
    register_unit(
        UnitSpec(
            type_name="N8nWorkflowExtract",
            input_ports=N8N_WORKFLOW_EXTRACTOR_INPUT_PORTS,
            output_ports=N8N_WORKFLOW_EXTRACTOR_OUTPUT_PORTS,
            step_fn=_n8n_workflow_extract_step,
            environment_tags_are_agnostic=True,
            description="Self-contained n8n workflow extractor (no external dependencies).",
        )
    )


__all__ = [
    "register_n8n_workflow_extract",
    "N8N_WORKFLOW_EXTRACTOR_INPUT_PORTS",
    "N8N_WORKFLOW_EXTRACTOR_OUTPUT_PORTS",
]
