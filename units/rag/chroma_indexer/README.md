# ChromaIndexer

**ChromaDB** chunk **upsert** (embed + `collection.add`) for the shared **`rag`** collection.

## Purpose

**Write-only workflow unit.** Feed parallel **`texts`** and **`metadatas`**; non-empty strings are embedded and added. Output is **`count`** (chunks added).

**Semantic search** → **RagSearch** (`rag/search.py` uses the **`query_semantic_raw`** helper from this package; that is not a unit port).

## Interface

| Port / Param | Direction | Type | Description |
|----------------|-----------|------|-------------|
| **Inputs** | `texts` | Any | List of chunk strings to index. |
| | `metadatas` | Any | Parallel list of metadata dicts per chunk. |
| **Output** | `count` | float | Number of chunks added. |
| **Params** | `persist_dir` | str | Index root (contains `chroma_db/`). |
| | `embedding_model` | str | Same model id as **Embedder**. |

Missing `persist_dir` or `embedding_model`, or empty **`texts`** → `count` 0.

## Python helpers

**`rag/indexer.py`** / **`rag/search.py`**: `add_rag_chunks`, `rebuild_rag_collection`, `get_rag_collection`, `chroma_safe_metadata`, `query_semantic_raw`.

## Notes

- Collection name is **`rag`**; space is **cosine**.
- Upsert uses **Embedder**-compatible **`encode_texts`** in batches.
