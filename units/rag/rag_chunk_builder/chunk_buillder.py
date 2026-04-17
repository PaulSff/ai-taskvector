from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit


RAG_CHUNK_BUILDER_INPUT_PORTS = [("items", "Any")]
RAG_CHUNK_BUILDER_OUTPUT_PORTS = [("chunks", "Any"), ("error", "str")]


# -----------------------------
# Chunking strategies
# -----------------------------

def _chunk_by_chars(
    text: str,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    if not text:
        return []

    chunks: list[str] = []
    i = 0
    n = len(text)

    while i < n:
        end = min(i + chunk_size, n)
        chunk = text[i:end]
        chunks.append(chunk)

        if end >= n:
            break

        i = end - overlap if overlap > 0 else end

    return chunks


def _chunk_by_lines(
    text: str,
    chunk_size: int,
) -> list[str]:
    lines = text.splitlines()
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0

    for line in lines:
        line_len = len(line) + (1 if buf else 0)

        if buf and buf_len + line_len > chunk_size:
            chunks.append("\n".join(buf))
            buf = [line]
            buf_len = len(line)
        else:
            buf.append(line)
            buf_len += line_len

    if buf:
        chunks.append("\n".join(buf))

    return chunks


# -----------------------------
# Core builder
# -----------------------------

def _build_chunks(
    items: list[dict[str, Any]],
    *,
    strategy: str,
    chunk_size: int,
    overlap: int,
) -> list[dict[str, Any]]:

    out: list[dict[str, Any]] = []

    for item in items:
        text = item.get("text", "")
        meta = item.get("metadata", {}) or {}

        if not isinstance(text, str) or not text.strip():
            continue

        if strategy == "lines":
            chunks = _chunk_by_lines(text, chunk_size)
        else:
            # default: chars
            chunks = _chunk_by_chars(text, chunk_size, overlap)

        n = len(chunks)

        for i, chunk in enumerate(chunks):
            out.append({
                "text": chunk,
                "metadata": {
                    **meta,
                    "chunk_index": i,
                    "chunk_count": n,
                },
            })

    return out


# -----------------------------
# Unit step
# -----------------------------

def _chunk_builder_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
):
    try:
        items = inputs.get("items")

        if not isinstance(items, list):
            return {"chunks": [], "error": "items must be a list"}, state

        # --- params ---
        strategy = str(params.get("strategy", "chars")).lower()
        chunk_size = int(params.get("chunk_size", 1000))
        overlap = int(params.get("overlap", 100))

        # --- safety guards ---
        chunk_size = max(100, min(chunk_size, 20000))
        overlap = max(0, min(overlap, chunk_size // 2))

        chunks = _build_chunks(
            items,
            strategy=strategy,
            chunk_size=chunk_size,
            overlap=overlap,
        )

        return {"chunks": chunks, "error": ""}, state

    except Exception as e:
        return {"chunks": [], "error": str(e)}, state


# -----------------------------
# Registration
# -----------------------------

def register_chunk_builder() -> None:
    register_unit(
        UnitSpec(
            type_name="ChunkBuilder",
            input_ports=RAG_CHUNK_BUILDER_INPUT_PORTS,
            output_ports=RAG_CHUNK_BUILDER_OUTPUT_PORTS,
            step_fn=_chunk_builder_step,
            environment_tags_are_agnostic=True,
            description="Universal text chunking unit (chars/lines strategies).",
        )
    )