"""
RagFlattenChunks: turn ``RagJsonIndexExtract`` / nested workflow ``chunks`` into parallel ``texts`` / ``metadatas``
lists for **Embedder** + **ChromaIndexer**, plus a compact ``extracted`` dict for **RagBuildIndexDocument**.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

RAG_FLATTEN_CHUNKS_INPUT_PORTS = [("data", "Any"), ("file_path_meta", "Any")]
RAG_FLATTEN_CHUNKS_OUTPUT_PORTS = [
    ("texts", "Any"),
    ("metadatas", "Any"),
    ("extracted", "Any"),
    ("error", "str"),
]


def _file_path_from_nested_outputs(data: Any) -> str:
    """RunWorkflow output includes nested ``inject_path`` → ``data`` (path string)."""
    if not isinstance(data, dict):
        return ""
    inj = data.get("inject_path")
    if isinstance(inj, dict):
        v = inj.get("data")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _chunks_from_data(data: Any) -> Any:
    """Chunk list, flat ``{chunks: ...}`` / ``{extract: {chunks}}``, or nested executor output."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        ex = data.get("extract")
        if isinstance(ex, dict) and "chunks" in ex:
            return ex.get("chunks")
        if "chunks" in data:
            return data.get("chunks")
        for ports in data.values():
            if isinstance(ports, dict) and ports.get("chunks") is not None:
                return ports.get("chunks")
    return None


def _rag_flatten_chunks_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    data_in = inputs.get("data")
    raw = _chunks_from_data(data_in)
    meta_in = inputs.get("file_path_meta")
    err = ""
    fp = ""
    if isinstance(meta_in, dict):
        fp = str(meta_in.get("file_path") or "").strip()
    elif isinstance(meta_in, str):
        fp = meta_in.strip()
    if not fp:
        fp = _file_path_from_nested_outputs(data_in)
    texts: list[str] = []
    metas: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            t = item.get("text")
            m = item.get("metadata")
            if not isinstance(m, dict):
                m = {}
            if t is None:
                continue
            s = str(t).strip()
            if not s:
                continue
            texts.append(s)
            mm = dict(m)
            if fp and "file_path" not in mm:
                mm["file_path"] = fp
            metas.append(mm)
    joined = "\n\n".join(texts)
    extracted: dict[str, Any] = {"body": joined, "chunk_count": float(len(texts))}
    if fp:
        extracted["file_path"] = fp
    return {"texts": texts, "metadatas": metas, "extracted": extracted, "error": err}, state


def register_rag_flatten_chunks() -> None:
    register_unit(
        UnitSpec(
            type_name="RagFlattenChunks",
            input_ports=RAG_FLATTEN_CHUNKS_INPUT_PORTS,
            output_ports=RAG_FLATTEN_CHUNKS_OUTPUT_PORTS,
            step_fn=_rag_flatten_chunks_step,
            description=(
                "Input ``data``: chunk list, ``{extract:{chunks}}`` / ``{chunks}``, or nested "
                "``{unit_id:{port:value}}`` (first ``chunks`` wins). "
                "``file_path_meta``: dict with ``file_path`` or bare path string. Outputs for RBD / Embedder / Chroma."
            ),
        )
    )


__all__ = [
    "register_rag_flatten_chunks",
    "RAG_FLATTEN_CHUNKS_INPUT_PORTS",
    "RAG_FLATTEN_CHUNKS_OUTPUT_PORTS",
]
