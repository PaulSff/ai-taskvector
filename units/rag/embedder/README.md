# Embedder

Encodes text with **sentence-transformers** for semantic RAG (same stack as `rag/indexer.py` and **ChromaIndexer**).

## Purpose

Turns one string or a list of strings into embedding vectors (L2-normalized by default for cosine similarity). Used in workflows between chunk producers (**RagBuildIndexDocument**, **RagJsonIndexExtract**) and **ChromaIndexer**, and internally by `encode_texts` from index/search helpers.

## Interface

| Port / Param | Direction | Type | Description |
|----------------|-----------|------|-------------|
| **Input** | `texts` | Any | Single `str` or `list[str]` |
| **Output** | `embeddings` | Any | `list[list[float]]` — one vector per non-empty input line |
| **Params** | `model_name` | str | HuggingFace / sentence-transformers id (e.g. `all-MiniLM-L6-v2` or `sentence-transformers/all-MiniLM-L6-v2`) |

Empty `model_name` or no texts → empty `embeddings`.

## Notes

- Models are cached per `(model_id, offline_flag)`; **`rag/ragconf`** offline mode sets `HF_HUB_OFFLINE` when loading.
- **`encode_texts`**, **`get_sentence_transformer`**, and **`normalize_sentence_transformer_model_id`** are importable from `units.rag.embedder.embedder` for non-graph code (e.g. `chroma_indexer`, `rag/search.py`).
