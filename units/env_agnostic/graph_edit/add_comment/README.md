# Add Comment

Add an assistant comment to the graph (metadata; not exported to runtimes). Env-agnostic; used in edit workflows.

## Purpose

Applies an add_comment edit: appends a comment (info, optional commenter) to the graph’s comments list. Validation in `assistants/graph_edits.apply_graph_edit`.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | any  | Current graph dict |
| **Outputs**  | graph     | any  | Graph with the comment added |
| **Params**   | config    | —    | `info` — comment text; optional `commenter` |

## Example

**Params:** `{"info": "Added valve per user request", "commenter": "assistant"}`  
**Input:** `{"graph": {"units": [...], "connections": [], "comments": []}}`  
**Output:** `{"graph": {..., "comments": [{"id": "...", "info": "Added valve...", "commenter": "assistant", "created_at": "..."}]}}`
