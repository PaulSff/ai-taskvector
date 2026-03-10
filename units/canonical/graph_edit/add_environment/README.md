# Add Environment

Add an environment tag to the graph so env-specific units become available. Env-agnostic; used in edit workflows.

## Purpose

Applies an add_environment edit: appends the given `env_id` (e.g. thermodynamic, data_bi, web) to the graph’s environments list. Validation in `assistants/graph_edits.apply_graph_edit`.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | graph     | any  | Current graph dict |
| **Outputs**  | graph     | any  | Graph with the environment added |
| **Params**   | config    | —    | `env_id` — environment id (e.g. thermodynamic, data_bi) |

## Example

**Params:** `{"env_id": "data_bi"}`  
**Input:** `{"graph": {"units": [...], "connections": [], "environments": ["thermodynamic"]}}`  
**Output:** `{"graph": {..., "environments": ["thermodynamic", "data_bi"]}}`
