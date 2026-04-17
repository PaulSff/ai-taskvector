"""
Build (text, metadata) pairs for RAG indexing from classified JSON.

Used only from :class:`units.rag.rag_json_index_extract.rag_json_index_extract.RagJsonIndexExtract`
inside the extraction workflow graph (``rag/workflows/json_kind_index_extract.json``).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from rag.extractors import (
    build_chat_history_index_documents,
    extract_canonical_workflow_meta,
    extract_n8n_workflow_meta,
    extract_node_red_catalogue_module,
    extract_node_red_workflow_meta,
    node_meta_to_text,
    workflow_meta_to_text,
)

_ORIGIN_FOR_KIND = {"n8n": "n8n", "node_red": "node-red", "canonical": "canonical"}


def chunks_for_json_kind(
    kind: str,
    path: Path,
    data: dict | list,
    source: str,
) -> list[tuple[str, dict[str, Any]]]:
    """
    Return zero or more ``(searchable_text, metadata)`` tuples for Chroma indexing.

    ``kind`` is the string from :func:`rag.content_types.registry.classify_json_for_rag`.
    """
    abs_path = str(path.resolve())
    src = source or path.name
    out: list[tuple[str, dict[str, Any]]] = []

    if kind == "n8n":
        if not isinstance(data, dict):
            return []
        meta = extract_n8n_workflow_meta(data, source=src)
        meta["file_path"] = abs_path
        meta["raw_json_path"] = abs_path
        meta["origin"] = _ORIGIN_FOR_KIND.get(kind, kind)
        return [(workflow_meta_to_text(meta), meta)]

    if kind == "canonical":
        if not isinstance(data, dict):
            return []
        meta = extract_canonical_workflow_meta(data, source=src)
        meta["file_path"] = abs_path
        meta["raw_json_path"] = abs_path
        meta["origin"] = _ORIGIN_FOR_KIND.get(kind, kind)
        return [(workflow_meta_to_text(meta), meta)]

    if kind == "node_red":
        meta = extract_node_red_workflow_meta(data, source=src)
        meta["file_path"] = abs_path
        meta["raw_json_path"] = abs_path
        meta["origin"] = _ORIGIN_FOR_KIND.get(kind, kind)
        return [(workflow_meta_to_text(meta), meta)]

    if kind == "chat_history":
        pairs = build_chat_history_index_documents(data, source=src, file_path=abs_path)
        return list(pairs)

    if kind == "node_red_catalogue":
        if not isinstance(data, dict):
            return []
        modules = data.get("modules")
        if not isinstance(modules, list):
            return []
        for mod in modules[:2000]:
            if not isinstance(mod, dict):
                continue
            meta = extract_node_red_catalogue_module(mod, source=src)
            meta["file_path"] = abs_path
            meta["url"] = mod.get("url") or ""
            text = node_meta_to_text(meta)
            out.append((text, meta))
        return out

    return []
