# ChromaIndexer

**ChromaDB** chunk **upsert** (embed + `collection.add`) for the shared **`rag`** collection.

## Purpose

**Write-only workflow unit.** Receives parallel **`texts`** and **`metadatas`** (and optionally pre-computed **`embeddings`**); non-empty strings are embedded and upserted. Output is **`count`** (chunks added).

## Responsibility split

| Unit | Responsibility |
|------|---------------|
| **ChromaIndexer** (this unit) | Write — add chunks to the index |
| **RagSearch** | Read — semantic search + path-based retrieval |
| **DeleteFromIndex** | Delete — remove chunks by `file_path` |

## Interface

| Port / Param | Direction | Type | Description |
|----------------|-----------|------|-------------|
| **Inputs** | `texts` | Any | List of chunk strings to index. |
| | `metadatas` | Any | Parallel list of metadata dicts per chunk. |
| | `embeddings` | Any | Optional pre-computed embedding vectors (one per chunk). |
| **Output** | `count` | float | Number of chunks added. |
| **Params** | `persist_dir` | str | Index root (contains `chroma_db/`). Use `settings.rag_index_data_dir`. |
| | `embedding_model` | str | Same model id as **Embedder**. Use `settings.rag_embedding_model`. |

Missing `persist_dir` or `embedding_model`, or empty **`texts`** → `count` 0.

## Public Python helper

`get_rag_collection(persist_dir)` — opens (or creates) the ChromaDB `rag` collection and returns the handle. Used by **RagSearch** and **DeleteFromIndex** units to access the same collection without re-opening the database.

All other internal helpers (`_add_rag_chunks`, `_rebuild_rag_collection`, `_chroma_safe_metadata`) are private implementation details of this unit.

## Notes

- Collection name is **`rag`**; distance space is **cosine**.
- Upsert uses **Embedder**-compatible **`encode_texts`** in batches of 64.
- Chunk IDs are SHA-256 hashes of `(global_index, file_path, text[:800])` — stable and deterministic.
