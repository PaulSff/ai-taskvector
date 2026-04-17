# NodeRedCatalogueExtract

Node-RED catalogue extractor aligned with extractors.py behavior.

## Purpose

Normalize and extract metadata from a Node-RED catalogue module (JSON/dict) into a single metadata item and short text summary for downstream RAG/indexing. Handles inline dicts or JSON files, collects id, description, keywords, types, categories, and URL; mirrors extractors.py-style behavior.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs** | `data` | Any | Root object (dict) containing the catalogue module; may be a wrapper with `graph` or `parsed`, or the module dict itself. |
|  | `file_path` | Any | Optional path override (string) used to read JSON file or set resolved file path. |
|  | `params` | Any | Not used; included for interface compatibility. |
| **Outputs** | `items` | Any | List with one item: {"text": "<summary>", "metadata": {…extracted meta…"}} or empty on error. |
|  | `error` | str | Error message when extraction fails; normally empty. |
| **Params** | (none required) | — | Unit is self-contained; no external params required. |

## Behavior / Rules

- Requires `data` to be a dict; otherwise returns an error "catalogue module must be a dict".
- Normalization: prefers `data["graph"]` or `data["parsed"]`, falling back to `data`.
- File-path handling:
  - Uses `data["file_path"]` unless `file_path` input is provided and non-empty (input overrides).
  - If resolved file path has a .json suffix and the normalized graph is not a dict, attempts to load JSON from that file.
  - If file read/parsing fails, returns the exception string in `error`.
- Metadata extraction (via _extract_catalogue_meta):
  - **content_type:** "node"
  - **format:** "node_red"
  - **id, name:** from module `id` (stringified); empty string if missing
  - **description:** from `description` (stringified)
  - **keywords:** list of strings from `keywords`
  - **node_types:** up to first 30 entries from `types`
  - **categories:** list of strings from `categories`
  - **url:** from `url` (stringified)
  - **source:** provided `source` field or filename (see file-path handling)
  - Additional fields added before output: **file_path**, **raw_json_path** (both set to resolved path string), **origin:** "node_red_catalogue"
- Text summary:
  - Built from name, description, joined keywords, joined categories, and up to first 15 node_types, joined with " | ".
- Output:
  - Returns a single item: {"text": "<summary>", "metadata": meta} inside `items`, and `error` empty on success.
  - On any exception, returns `items: []` and `error` set to the exception message.

## Notes / Defaults

- String coercion:
  - None -> ""
  - lists/dicts -> JSON string when possible, otherwise str()
  - Other values -> str()
- Lists are normalized to string lists; empty or whitespace-only strings become [].
- node_types list is truncated to 30 for metadata and to 15 for text summary.

## Example

Input:

```python
data = {
  "id": "node-123",
  "description": "A sample node",
  "keywords": ["io","sensor"],
  "types": ["input.sensor","output.log"],
  "categories": ["hardware"],
  "url": "https://example.com/node-123",
  "source": "catalogue.json"
}
```

Output:

```python
{
  "items": [
    {
      "text": "node-123 | A sample node | io sensor | hardware | input.sensor output.log",
      "metadata": {
        "content\_type": "node",
        "format": "node\_red",
        "id": "node-123",
        "name": "node-123",
        "source": "catalogue.json",
        "description": "A sample node",
        "keywords": ["io","sensor"],
        "node\_types": ["input.sensor","output.log"],
        "categories": ["hardware"],
        "url": "https://example.com/node-123",
        "file\_path": ".",
        "raw\_json\_path": ".",
        "origin": "node\_red\_catalogue"
      }
    }
  ],
  "error": ""
}
```
