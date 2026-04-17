"""
RagJsonIndexExtract unit: build RAG ``chunks`` from JSON using :func:`rag.json_index_chunks.chunks_for_json_kind`.

Params: ``json_kind`` (same strings as :func:`rag.content_types.registry.classify_json_for_rag`).
Input ``data``: dict with ``graph`` or ``parsed`` (dict/list, optional), optional ``file_path`` and
``source`` keys. Optional wired inputs: ``file_path`` (overrides dict key), ``kind_in`` (overrides
``params.json_kind``). When the graph root is missing and ``file_path`` points to a readable
``.json`` file, JSON is loaded here, then classified if ``json_kind`` is empty or ``generic``.
Output ``chunks``: list of ``{"text": str, "metadata": dict}`` for downstream Embedder / ChromaIndexer.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

RAG_JSON_INDEX_EXTRACT_INPUT_PORTS = [("data", "Any"), ("file_path", "Any"), ("kind_in", "Any")]
RAG_JSON_INDEX_EXTRACT_OUTPUT_PORTS = [("chunks", "Any"), ("error", "str")]


def _rag_json_index_extract_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from rag.content_types.registry import classify_json_for_rag
    from rag.json_index_chunks import chunks_for_json_kind

    raw = inputs.get("data")
    err = ""
    kind = str(params.get("json_kind") or "").strip() or "generic"
    ki = inputs.get("kind_in")
    if isinstance(ki, str) and ki.strip():
        kind = ki.strip()
    if not isinstance(raw, dict):
        return {"chunks": [], "error": "data must be a dict with graph, file_path, source"}, state

    graph = raw.get("graph")
    if graph is None:
        graph = raw.get("parsed")
    if graph is None and isinstance(raw, dict) and "graph" not in raw and "parsed" not in raw:
        graph = raw
    fp = str(raw.get("file_path") or "").strip()
    fp_w = inputs.get("file_path")
    if isinstance(fp_w, str) and fp_w.strip():
        fp = fp_w.strip()
    src = str(raw.get("source") or "").strip() or Path(fp).name if fp else ""

    if fp:
        path = Path(fp)
    else:
        path = Path(".")

    if graph is None and fp and path.suffix.lower() == ".json" and path.is_file():
        try:
            graph = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError) as e:
            return {"chunks": [], "error": str(e)}, state

    if isinstance(graph, (dict, list)) and kind in ("", "generic"):
        inferred = classify_json_for_rag(path, graph)
        if inferred:
            kind = inferred

    try:
        pairs = chunks_for_json_kind(kind, path, graph, src)
    except Exception as e:
        return {"chunks": [], "error": str(e)}, state

    chunks = [{"text": t, "metadata": dict(m)} for t, m in pairs]
    return {"chunks": chunks, "error": err}, state


def register_rag_json_index_extract() -> None:
    register_unit(
        UnitSpec(
            type_name="RagJsonIndexExtract",
            input_ports=RAG_JSON_INDEX_EXTRACT_INPUT_PORTS,
            output_ports=RAG_JSON_INDEX_EXTRACT_OUTPUT_PORTS,
            step_fn=_rag_json_index_extract_step,
            environment_tags_are_agnostic=True,
            description="Params.json_kind + input data {graph, file_path, source} → output chunks for RAG index.",
        )
    )


__all__ = [
    "register_rag_json_index_extract",
    "RAG_JSON_INDEX_EXTRACT_INPUT_PORTS",
    "RAG_JSON_INDEX_EXTRACT_OUTPUT_PORTS",
]
