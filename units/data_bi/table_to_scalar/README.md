# TableToScalar

Extract a single scalar from a table by column and aggregation (first, sum, mean, etc.).

## Purpose

Pandas supports `df['A'].sum()`, `df['B'].mean()`, and indexing for the first value. This unit exposes that so downstream nodes (e.g. merge_llm) can consume one value per port instead of a full table.

- **first** (default): value of the column in the first row.
- **last**: value in the last row.
- **sum**, **mean**, **min**, **max**: numeric aggregation over the column.
- **default**: used when the table is empty or the column is missing.

## Interface

| Port / Param | Direction | Type   | Description                          |
|--------------|-----------|--------|--------------------------------------|
| **Inputs**   | table     | table  | input table                          |
|              | column    | str    | column name to read                  |
|              | agg       | str    | "first", "last", "sum", "mean", "min", "max" (default: first) |
|              | default   | Any    | value when empty or column missing   |
| **Outputs**  | row_count | float  | number of rows                       |
|              | value     | Any    | extracted scalar                     |

## Example

**Input:** `{"table": [{"A": 1}, {"A": 2}, {"A": 3}], "column": "A", "agg": "sum"}`  
**Output:** `row_count=3`, `value=6`.

**Input:** `{"table": [{"line": "- run_workflow: ..."}], "column": "line", "agg": "first", "default": ""}`  
**Output:** `value="- run_workflow: ..."` (or `""` if table is empty after a filter).
