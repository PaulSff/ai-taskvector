# RagBuildIndexDocument

Builds **one RAG index row**: searchable `text` plus Chroma-safe **`metadata`**, and a combined **`document`** object for **Embedder** / **ChromaIndexer** upserts.

## Purpose

Takes **RagExtract** output (`extracted`) plus **`file_path`**, formats **`text`** with **`str.format_map`** against extracted keys (missing keys → empty string), then copies selected keys into **`metadata`** and merges **`static_metadata`**. Sets `file_path` on metadata when provided.

## Interface

| Port / Param | Direction | Type | Description |
|----------------|-----------|------|-------------|
| **Inputs** | `extracted` | Any | Flat dict (e.g. from **RagExtract**) |
| | `file_path` | str | Indexed file path (stored on metadata) |
| **Outputs** | `text` | str | Formatted body for embedding |
| | `metadata` | Any | Dict for Chroma |
| | `document` | Any | `{"text", "metadata"}` convenience object |
| | `error` | str | Set if `text_template` formatting fails |
| **Params** | `text_template` | str | Default `{body}`; `{key}` placeholders use `extracted` |
| | `metadata_keys` | list[str] | Which keys from `extracted` to copy into metadata |
| | `static_metadata` | dict | Merged after extracted keys |

## Example

Wire **extracted** from **RagExtract**, **file_path** from inject/merge, then fan out **`text`** / **`metadatas`** lists into **ChromaIndexer** or into batch helpers in **`rag/indexer.py`**.
