# FileTypeDetector

Maps a **file path** to RAG **content-type registry** fields for routing and indexing.

## Purpose
Content classification.
Uses `rag.content_types.registry.upload_router_payload`. **Input `data` is only a file path** (`str` or `os.PathLike` such as `pathlib.Path`), not a `{file_path, parsed}` dict. The path string is stored on the output **as given** (no `resolve()`). For pre-parsed structured content, pass `parsed_data` to the second input `parsed_data` as a `dict`. 

Neither the unit, nor the registry parses files itself. The `pre-parsed` gets passed through to the downstream units, if present.

## Interface

| Port / Param | Direction | Type | Description |
|----------------|-----------|------|-------------|
| **Input** | `data` | str or PathLike | Path to the file on disk |
| **Input** | `parsed_data` | dict | Pre-parsed data form upstream (optional) |
| **Outputs** | `content_type_id` | str | Package id from registry (e.g. `node-red-workflow`) |
| | `content_kind` | str | Semantic content classification label from discriminants (e.g. `node_red`, `markdown`, `generic`) |
| | `family` | str | A top-level content family (e.g. markdown) |
| | `payload` | Any | Router dict (`file_path`, `parsed`, `content_kind`, `content_type_id`, `family`) |
| | `parsed` | Any | Same as `payload["parsed"]` (e.g. loaded JSON for `.json`) |
| | `error` | str | Set when the path is invalid type or classification / read fails |

## Examples

1. Only sending a file path

Input:

```json
inputs = {
    "data": /data/users.csv,
    # "parsed_data" is omitted
}
```

Outputs:

outputs["parsed"]       # None, because no parsed data was provided
outputs["content_kind"] # Determined by the registry
outputs["family"]       # Determined by the registry
outputs["error"]        # Should be empty if file_path is valid

2. Sending both pre-parsed data and file path

Suppose your upstream unit already parsed a CSV file:

```json
inputs = {
    "data": /data/users.csv,
    "parsed_data": {
        "columns": ["id", "name", "email"],
        "rows": [
            [1, "Alice", "alice@example.com"],
            [2, "Bob", "bob@example.com"],
        ],
        "metadata": {"source": "..."},
    },
}
```

Outputs:

outputs["parsed"]       # Should match `pre_parsed_csv` dict
outputs["content_kind"] # Determined by the registry
outputs["family"]       # Determined by the registry

## Workflow sketch 

**Inject** `data` = `"/path/to/file.json"` (string path) → **FileTypeDetector** → **Router** on `payload.content_type_id`; downstream **PayloadTransform** → **RunWorkflow** per `content_type.yaml`.
