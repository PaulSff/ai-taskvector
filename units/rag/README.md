# `units/rag` — RAG workflow units

Python package for **retrieval-augmented generation** units: index build (Docling, JSON chunks), embeddings, ChromaDB, search, prompt formatting, and ingest helpers.

## Registration

Call **`register_rag_units()`** (or rely on **`ensure_full_unit_registry()`** / **`ensure_all_environment_units_registered()`**, which load the **`rag`** environment via `units/env_loaders.py`).

All types below are tagged with **`environment_tags: ["rag"]`** and **`environment_tags_are_agnostic: true`** so they appear alongside canonical workflow units when the registry is fully loaded.

## Units (by folder)

| Type | Folder | Role |
|------|--------|------|
| **RagSearch** | `rag_search/` | Semantic / path search over the persisted index |
| **RagDetectOrigin** | `rag_detect_origin/` | Infer import origin for workflow JSON |
| **RagUpdate** | `rag_update/` | Incremental index maintenance |
| **RagPickDelegatee** | `rag_pick_delegatee/` | Pick delegate role from nested RAG table |
| **FormatRagPrompt** | `format_rag_prompt/` | RAG result table → prompt block string |
| **LoadDocument** | `load_document/` | Docling → text + tables for doc-to-text flows |
| **Embedder** | `embedder/` | sentence-transformers encoding |
| **ChromaIndexer** | `chroma_indexer/` | Chroma chunk upsert (writes); search → **RagSearch** |
| **RagContentClassify** | `rag_content_classify/` | Declarative labels (Router-style rules) |
| **RagExtract** | `rag_extract/` | Flat dict from dot paths on JSON |
| **RagBuildIndexDocument** | `rag_build_index_document/` | One `{text, metadata}` row for indexing |

Application RAG logic (extractors, content types, indexer orchestration) lives in the top-level **`rag/`** package, not under `units/rag/`.

## Gym / native env (RL)

For **`GraphEnv`** with primary **`environment_type: rag`**, see **`environments/native/rag/`** (`RagEnvironmentSpec`, `load_rag_env`) and **`EnvironmentType.RAG`** in `core/schemas/process_graph.py` (wired in `core/env_factory/build_env`).
