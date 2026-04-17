# RagContentClassify

Assigns a **string label** to structured input using declarative rules (same spirit as **Router**).

## Purpose

Walks **`params.classifications`**: a list of `{ "label": "...", "all": [rules...] }` or `{ "label": "...", "any": [rules...] }`. The first block whose rules match **`input.data`** wins; otherwise **`params.default_label`** (default `unclassified`). Use after **FileTypeDetector** / registry payloads or **RagExtract** to branch extraction workflows without code.

## Interface

| Port / Param | Direction | Type | Description |
|----------------|-----------|------|-------------|
| **Input** | `data` | Any | Typically a dict (router payload, merged inject data, etc.) |
| **Outputs** | `label` | str | Chosen classification label |
| | `data` | Any | Same object passed through |
| | `error` | str | Reserved; normally empty |
| **Params** | `classifications` | list | Blocks with `label` and `all` or `any` rule lists |
| | `default_label` | str | Fallback when no block matches |

## Rules

Each rule is a dict with optional **`field`** (dot path into `data`) and one of: **`exists`**, **`equals`**, **`equals_str`**, **`ends_with`**, **`starts_with`**, **`contains`**, **`regex`**. Semantics match **Router**-style matching.

## Example

**Params:** `{"default_label": "other", "classifications": [{"label": "workflow", "all": [{"field": "content_type_id", "equals_str": "node-red-workflow"}]}]}`
