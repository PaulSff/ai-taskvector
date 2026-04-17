# RagFlattenChunks

Converts a list of RAG **chunks** (`{"text": str, "metadata": dict}`) into the normalized shapes needed by the indexing pipeline:

- `texts`: list of strings (for **Embedder**)
- `metadatas`: list of dicts (for **ChromaIndexer**)
- `extracted`: compact dict for **RagBuildIndexDocument** (`body`, `chunk_count`, optional `file_path`)

## Purpose

`RagFlattenChunks` is an **adapter/formatter** unit. It does not decide how to extract text from a file; it standardizes whatever chunk list is produced by an upstream extractor (often a nested `RunWorkflow`).

It can consume chunks in several common shapes:

- A **chunk list** directly: `[{"text": "...", "metadata": {...}}, ...]`
- A dict with **`chunks`**: `{"chunks": [...]}` (e.g. unit output dict)
- A dict with **`extract.chunks`**: `{"extract": {"chunks": [...]}}`
- A **nested executor output** dict (e.g. from `RunWorkflow`): `{unit_id: {port_name: value}}` (first `chunks` it finds wins)

## Interface

| Port / Param | Direction | Type | Description |
|----------------|-----------|------|-------------|
| **Inputs** | `data` | Any | Any of the chunk container shapes above |
| | `file_path_meta` | Any | Optional `{"file_path": "..."}` or `"..."` to force a `file_path` into each chunk metadata |
| **Outputs** | `texts` | Any | List of non-empty chunk text strings |
| | `metadatas` | Any | List of metadata dicts (aligned with `texts`) |
| | `extracted` | Any | `{"body": "<joined texts>", "chunk_count": <float>, "file_path": "<optional>"}` |
| | `error` | str | Reserved; normally empty |

## Notes

- Empty / missing chunks produce empty `texts`/`metadatas` and `extracted.body == ""`.
- `chunk_count` is a float for consistency with other pipeline units.
- If `file_path_meta` is not provided, the unit tries to infer a path from nested workflow outputs (e.g. `inject_path.data`).
