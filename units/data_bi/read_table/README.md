# ReadTable

Load a table from a file path (CSV, JSON, JSONL, Parquet, XLSX, XLS). Caches in state unless `reload` is set.

## Purpose

Reads tabular data from disk. Format is inferred from params or path. Output includes row count, table, and schema (column names). Useful as the entry point for file-based data flows.

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | in        | str    | `path` — file path             |
| **Outputs**  | out       | float  | `row_count`                    |
|              | out       | table  | `table` — loaded rows          |
|              | out       | list   | `schema` — column names        |
| **Params**   | config    | —      | `path`, `format` (csv, json, jsonl, parquet, xlsx, xls), `reload`, `read_formulas` |

## Examples

**Params:** `{"path": "/data/sales.csv", "format": "csv"}` or `{"path": "/data/sales.xlsx", "format": "xlsx", "read_formulas": false}`
**Output:** `{"row_count": 1000, "table": [...], "schema": ["id", "date", "amount"]}`

With `read_formulas: true` for xlsx/xls, formula cells will contain strings like `=A1+B1` instead of numeric values.
