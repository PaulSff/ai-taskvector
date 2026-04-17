# RagNodeRedWorkflowExtract

Self-contained Node-RED workflow extractor (aligned with extractors.py node-red behavior).

## Purpose

Normalize and extract metadata from a Node-RED workflow JSON/dict into a single metadata item and short text summary for downstream RAG/indexing. Handles inline dicts, top-level node lists, or JSON files, truncates long fields, and mirrors extractors.py node-red behavior (unit types, labels, counts, summary/readme).

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs** | `data` | Any | Root object (dict or list) containing the workflow; may be the full wrapper, `graph`, `parsed`, a top-level node list, or a flows wrapper. |
|  | `file_path` | Any | Optional path override (string) used to read JSON file or set source/file path. |
|  | `params` | Any | Optional params dict (exposed constant slot). |
| **Outputs** | `items` | Any | List with one item: {"text": "<summary>", "metadata": {…extracted meta…"}} or empty on error. |
|  | `error` | str | Error message when extraction fails; normally empty. |
| **Params** | `label_limit` | int | Max number of labels to include (default: 20). |
|  | `summary_limit` | int | Max length for stored summary (default: 500). |
|  | `readme_limit` | int | Max length for stored readme (default: 2000). |

## Behavior / Rules

- Accepts `data` as a dict or list; if not dict/list returns an error.
- Normalization: if `data` is dict, prefers `data["graph"]` or `data["parsed"]`, falling back to `data` itself.
- If a file path is provided (in `data["file_path"]` or `file_path` input) and the workflow content is not a dict, attempts to load JSON from that .json file.
- Extracts nodes from:
  - top-level list (treated as nodes),
  - `nodes` key,
  - `flow` key,
  - `flows` wrapper (inspects first element for nodes or list-of-nodes).
- Gathers:
  - **content_type:** "workflow"
  - **format:** "node_red"
  - **name:** from tab label/name when a node of type "tab" exists; fallback to flows[0].label/name; then summary/readme fallback; otherwise "Unknown"
  - **source:** from `source` or filename
  - **unit_types:** unique set of node `"type"` values (last segment after '.')
  - **labels:** node `"label"` or `"name"` values, excluding "tab" nodes, truncated to `label_limit`
  - **node_count:** number of nodes with truthy `type`
  - **summary:** if present on the graph (truncated to `summary_limit`)
  - **readme:** if present on the graph (truncated to `readme_limit`)
  - **file_path** and **raw_json_path:** set to resolved path
  - **origin:** "node_red_workflow"
- Produces a single text summary combining name, origin, description (if present, truncated for text), node types, nodes (first 10 labels), summary, readme (truncated to 500), and format — joined with " | ".
- No chunking: returns one item with `text` and `metadata`.

## Defaults

- DEFAULT_NAME_FALLBACK: "Unknown"  
- DEFAULT_LABEL_LIMIT: 20  
- DEFAULT_SUMMARY_LIMIT: 500  
- DEFAULT_README_LIMIT: 2000

## Example

Input (params: default):

```python
data = {
  "nodes": [{"type":"tab","label":"Main"},{"type":"http in","name":"Get"},{"type":"function","name":"Process"}],
  "summary": "Example flow",
  "source": "flow.json"
}
```
