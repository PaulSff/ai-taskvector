# RagJsonIndexExtract

Turns workflow **JSON** into a list of **`{text, metadata}`** chunks for indexing, using **`rag.json_index_chunks.chunks_for_json_kind`**.

## Purpose

Parameterized **`json_kind`** selects the chunking strategy (aligned with **`rag.content_types.registry.classify_json_for_rag`** labels: e.g. Node-RED flow, n8n, generic). Output feeds **Embedder** + **ChromaIndexer** or **`rag/indexer.py`**-style pipelines.

## Interface

| Port / Param | Direction | Type | Description |
|----------------|-----------|------|-------------|
| **Input** | `data` | Any | Dict with **`graph`** (dict or list), **`file_path`** (str), optional **`source`** (str) |
| **Outputs** | `chunks` | Any | List of `{ "text": str, "metadata": dict }` |
| | `error` | str | Parse / chunk errors; empty on success |
| **Params** | `json_kind` | str | Kind id passed to `chunks_for_json_kind` (default `generic`) |

Non-dict **`data`** → empty `chunks` and an error message.

## Example

After **JsonParser** + path merge, set **`json_kind`** from **FileTypeDetector** / **Router** and connect **`chunks`** to a unit that expands into **ChromaIndexer** `texts` / `metadatas` lists.
