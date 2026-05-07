# DeleteFromIndex

**Type:** `DeleteFromIndex`  
**Domain:** `rag`

## Purpose

Removes chunks from the ChromaDB RAG index by `metadata.file_path`. This is the counterpart to **ChromaIndexer** (write) and **RagSearch** (read): it handles targeted deletion of specific indexed documents without requiring a full index rebuild.

Each path is tried both as-is and resolved to an absolute path, matching whichever form was used at index time. After deletion the **RagSearch** LRU cache is cleared automatically.

## Ports

| Direction | Name | Type | Description |
|-----------|------|------|-------------|
| Input | `file_paths` | `Any` | List of file path strings (or a single string) whose chunks should be deleted |
| Output | `count` | `float` | Total number of chunk IDs removed from the index |
| Output | `error` | `str` | Error message string, or `null` on success |

## Params

| Name | Type | Description |
|------|------|-------------|
| `persist_dir` | `str` | Path to the ChromaDB persistence directory. Use `settings.rag_index_data_dir` in workflow JSON. |

## Workflow

Use `rag/workflows/rag_delete_from_index.json` to invoke this unit from an orchestrator or CLI:

```json
{
  "initial_inputs": {
    "inject_paths": { "data": ["/abs/path/to/file.md"] }
  }
}
```

## Responsibility split

| Unit | Responsibility |
|------|---------------|
| **ChromaIndexer** | Write — add chunks to the index |
| **RagSearch** | Read — semantic search + path-based retrieval |
| **DeleteFromIndex** | Delete — remove chunks by `file_path` |

## Python helper

`delete_chunks_by_file_paths(*, persist_dir, file_paths)` is also importable directly for use in `rag/indexer.py` or scripts that need programmatic deletion without running a workflow.
