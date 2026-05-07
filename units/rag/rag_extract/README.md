# RagExtract

Builds a list of flat dictionaries from input JSON using dot paths and optional constants.

## Purpose

Map nested workflow or router data into a flat structure expected by downstream units (for example, RagBuildIndexDocument or RunWorkflow's initial inputs). Only dictionary key traversal is supported; missing paths yield JSON-friendly nulls (None) and non-JSON-serializable values are coerced to strings.

## Interface

| Port / Param | Direction | Type | Description |
|--------------:|:---------:|:----:|-------------|
| **data** | Input | Any | Root object to extract from (single dict/object or a list of objects). |
| **items** | Output | Any | A list of flat dicts produced from `paths` (one entry per input element; single input → single-element list). |
| **error** | Output | str | Reserved; currently always an empty string. |
| **paths** | Param | list[dict] | Extraction rules. Each entry is either `{"out": "key", "from": "nested.path"}` or `{"out": "key", "constant": <any>}`. `out` may also be specified as `key`; `from` may also be `path`. |

Notes:

- Each `paths` item must be a dict. Non-dict entries are ignored.
- `out`/`key` is required (coerced to string and trimmed); entries missing it are skipped.
- For constants use the `constant` field; for extracting from the input object use `from` (dot path).
- The extractor only traverses dict keys. If a path step encounters a non-dict, the result for that key is `null` (`None`).
- Values are returned as-is when JSON-serializable; otherwise they are converted to strings.

## Behavior & Edge Cases

- If `data` is a list, extraction is applied to each element and `items` is a list of extracted dicts.
- If `data` is a single object (not a list), `items` is a single-element list containing the extracted dict.
- If `data` is `None`, `items` is an empty list.
- Missing keys along a path produce `None` for that output key.
- Path parts that are empty (e.g., consecutive dots) are ignored.
- The unit does not validate or surface errors; `error` remains an empty string in current implementation.

## Examples

### Single object

- Params:

```json
{"paths": [{"out":"id","from":"meta.id"},{"out":"type","constant":"note"}]}
```

- Data:

```json
{"meta": {"id": 5}, "other": 1}
```

- Output `items`:

```json
[{"id": 5, "type": "note"}]
```

### List of objects

- Params:

```json
{"paths": [{"out":"title","from":"label"}, {"out":"source","constant":"upload"}]}
```

- Data:

```json
[{"label":"A"},{"label":"B"}]
```

- Output `items`:

```json
[{"title":"A","source":"upload"},{"title":"B","source":"upload"}]
```
