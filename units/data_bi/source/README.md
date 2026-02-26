# DataSource

Outputs a table from params (inline `data` or `path` to load) or from state. No input ports; used as a flow source.

## Purpose

Provides tabular data to the flow: either from `params.data`, or by reading from `params.path` (CSV/JSON). Result is cached in state. Typical entry node for data/BI pipelines.

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | —         | —      | None                            |
| **Outputs**  | out       | float  | `row_count`                     |
|              | out       | table  | `table` — data                  |
|              | out       | list   | `schema` — column names         |
| **Params**   | config    | —      | `data` (list of dicts), `path`, `format` |

## Example

**Params:** `{"path": "data.json", "format": "json"}`  
**Output:** `{"row_count": 10, "table": [...], "schema": ["a", "b"]}`
