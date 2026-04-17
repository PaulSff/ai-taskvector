# RagExtract

Builds a **flat dict** from input JSON using dot paths and optional constants.

## Purpose

Maps nested workflow or router data into keys expected by **RagBuildIndexDocument** (`text_template`, `metadata_keys`) or downstream **RunWorkflow** `initial_inputs`. Only **dict** key traversal is supported; missing paths become JSON-friendly nulls / strings.

## Interface

| Port / Param | Direction | Type | Description |
|----------------|-----------|------|-------------|
| **Input** | `data` | Any | Root object (usually dict) |
| **Outputs** | `extracted` | Any | Flat dict built from `paths` |
| | `error` | str | Reserved; normally empty |
| **Params** | `paths` | list | Items like `{"out": "body", "from": "payload.nodes"}` or `{"out": "kind", "constant": "node_red"}` |

Each item supports **`out`** or **`key`** as the destination key, and either **`from`** / **`path`** (dot path) or **`constant`**.

## Example

**Params:** `{"paths": [{"out": "title", "from": "label"}, {"out": "source", "constant": "upload"}]}`
