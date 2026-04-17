# FileTypeDetector

Maps a **file path** to RAG **content-type registry** fields for routing and indexing.

## Purpose

Uses `rag.content_types.registry.upload_router_payload`. **Input `data` is only a file path** (`str` or `os.PathLike` such as `pathlib.Path`), not a `{file_path, parsed}` dict. The path string is stored on the output **as given** (no `resolve()`). For `.json` files, the registry loads the file (when readable) and fills `payload["parsed"]` / classification from that content.

## Interface

| Port / Param | Direction | Type | Description |
|----------------|-----------|------|-------------|
| **Input** | `data` | str or PathLike | Path to the file on disk |
| **Outputs** | `content_type_id` | str | Package id from registry (e.g. `node-red-workflow`) |
| | `json_kind` | str | Discriminant label for JSON (e.g. `node_red`); empty for non-JSON |
| | `suffix` | str | File suffix from path |
| | `payload` | Any | Router dict (`file_path`, `parsed`, `json_kind`, `content_type_id`, …) |
| | `parsed` | Any | Same as `payload["parsed"]` (e.g. loaded JSON for `.json`) |
| | `error` | str | Set when the path is invalid type or classification / read fails |

## Example

**Inject** `data` = `"/path/to/file.json"` (string path) → **FileTypeDetector** → **Router** on `payload.content_type_id`; downstream **PayloadTransform** → **RunWorkflow** per `content_type.yaml`.

For in-memory JSON only (no file yet), use **JsonParser** / other units upstream of routing, or write a temp file and pass its path here.
