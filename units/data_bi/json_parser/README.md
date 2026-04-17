# JsonParser

Parses JSON from a string (or passes through dict/list) for pipelines that classify or extract structured data.

## Purpose

Normalizes **Inject** output (raw JSON text) into `parsed` for **RagContentClassify**, **RagExtract**, or other units that consume structured JSON. **FileTypeDetector** expects a **file path string** only; use it on a path and read `payload.parsed` / the **`parsed`** output when the JSON lives on disk. Optional **wrap_top_level_list** wraps a root JSON array as `{"nodes": [...]}`.

## Interface

| Port / Param | Direction | Type | Description |
|----------------|-----------|------|-------------|
| **Input** | `data` | Any | JSON string, bytes, or already-parsed dict/list |
| **Outputs** | `parsed` | Any | Parsed object or `null` on failure |
| | `error` | str | Parse error message; empty on success |
| **Params** | `wrap_top_level_list` | bool | If true and root is an array, wrap as `{"nodes": array}` |

## Example

**Inject** (path string) → **FileTypeDetector** → **Router** when JSON is already a file. **Inject** (raw JSON text) → **JsonParser** → … when starting from in-memory text (combine with a path via your own merge / temp file if you also need **FileTypeDetector** on a path).
