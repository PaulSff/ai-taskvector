# RagCanonicalWorkflowExtract

Self-contained canonical workflow extractor (aligned with extractors.py canonical behavior).

## Purpose

Normalize and extract metadata from a "canonical" workflow JSON/dict into a single metadata item and short text summary for downstream RAG/indexing. Handles inline dicts or JSON files, truncates long fields, and mirrors canonical extractor behavior (unit types, labels, counts, summary/readme).

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs** | `data` | Any | Root object (expected dict) containing the workflow; may be the full wrapper, `graph`, or `parsed` field. |
|  | `file_path` | Any | Optional path override (string) used to read JSON file or set source/file path. |
| **Outputs** | `items` | Any | List with one item: {"text": "<summary>", "metadata": {…extracted meta…"}} or empty on error. |
|  | `error` | str | Error message when extraction fails; normally empty. |
| **Params** | `label_limit` | int | Max number of labels to include (default: 20). |
|  | `desc_limit` | int | Max length for stored description (default: 4000). |

## Behavior / Rules

- Accepts `data` as a dict; if `data` is not a dict returns an error.
- Normalization: prefers `data["graph"]` or `data["parsed"]` as the workflow content, falling back to `data` itself.
- If a file path is provided (in `data["file_path"]` or `file_path` input) and the workflow content is not a dict, attempts to load JSON from that .json file.
- Extracts unit list from the `units` field (only dict entries counted).
- Gathers:
  - **content_type:** "workflow"
  - **format:** "canonical"
  - **name:** from `name` or fallback "Canonical graph"
  - **source:** from `source` or filename
  - **unit_types:** unique set of unit `"type"` values
  - **labels:** unit `"id"` values, truncated to `label_limit`
  - **node_count:** number of units
  - **description:** if present, truncated to `desc_limit`
  - **file_path** and **raw_json_path:** set to resolved path
  - **origin:** "canonical"
  - **summary** and **readme:** if present on the graph (summary truncated to 500, readme to 2000)
- Produces a single text summary combining name, origin, description (truncated to 2000 for text), node types, integrations, nodes (first 10 labels), summary, readme (truncated to 500), and format — joined with " | ".
- No chunking: returns one item with `text` and `metadata`.

## Defaults

- DEFAULT_NAME_FALLBACK: "Canonical graph"  
- DEFAULT_LABEL_LIMIT: 20  
- DEFAULT_DESC_LIMIT: 4000

## Example

Input (params: default):
```python
data = {
  "name": "My Workflow",
  "units": [{"id": "n1", "type": "task"}, {"id": "n2", "type": "task"}],
  "description": "A sample workflow.",
  "source": "upload.json"
}
```

Output:

```python
items = [{
  "text": "Workflow: My Workflow | A sample workflow. | Node types: task | Nodes: n1, n2 | Format: canonical",
  "metadata": {
    "content\_type":"workflow",
    "format":"canonical",
    "name":"My Workflow",
    "source":"upload.json",
    "unit\_types":["task"],
    "labels":["n1","n2"],
    "node\_count":2,
    "description":"A sample workflow.",
    "file\_path":".",
    "raw\_json\_path":".",
    "origin":"canonical"
  }
}]
error = ""
```
