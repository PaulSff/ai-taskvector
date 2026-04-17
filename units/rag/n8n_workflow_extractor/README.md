# RagN8nWorkflowExtract

Self-contained n8n workflow extractor (aligned with extractors.py n8n behavior).

## Purpose

Normalize and extract metadata from an n8n workflow JSON/dict into a single metadata item and short text summary for downstream RAG/indexing. Handles inline dicts or JSON files, collects integrations, labels, node counts, and mirrors extractors.py n8n behavior.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs** | `data` | Any | Root object (dict) containing the workflow; may be the full wrapper, `graph`, `parsed`, or the workflow dict. |
|  | `file_path` | Any | Optional path override (string) used to read JSON file or set source/file path. |
| **Outputs** | `items` | Any | List with one item: {"text": "<summary>", "metadata": {…extracted meta…"}} or empty on error. |
|  | `error` | str | Error message when extraction fails; normally empty. |
| **Params** | (none required) | — | Unit is self-contained; truncation defaults documented below. |

## Behavior / Rules

- Accepts `data` as a dict; if not dict returns an error.
- Normalization: prefers `data["graph"]` or `data["parsed"]`, falling back to `data` itself.
- If a file path is provided (in `data["file_path"]` or `file_path` input) and the workflow content is not a dict, attempts to load JSON from that .json file.
- Extracts nodes from `nodes` key (defaults to empty list if missing).
- Gathers:
  - **content_type:** "workflow"
  - **format:** "n8n"
  - **name:** `name` field from workflow or `meta.instanceId` fallback; otherwise "Unknown"
  - **source:** from `source` or filename
  - **integrations:** unique set of integration names derived from node `type` (last segment after '.')
  - **labels:** node `name` values, truncated to 20
  - **node_count:** len(nodes)
  - **file_path** and **raw_json_path:** set to resolved path
  - **origin:** "n8n_workflow"
- Produces a single text summary combining name, integrations, node labels (first 10), format — joined with " | ".
- No chunking: returns one item with `text` and `metadata`.

## Defaults

- DEFAULT_NAME_FALLBACK: "Unknown"  
- DEFAULT_LABEL_LIMIT: 20

## Example

Input (params: default):

```python
data = {
  "nodes": [{"type":"n8n-nodes-base.httpRequest","name":"Fetch"},{"type":"n8n-nodes-base.function","name":"Process"}],
  "name": "Example workflow",
  "source": "workflow.json"
}
