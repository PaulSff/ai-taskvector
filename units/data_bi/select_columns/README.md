# SelectColumns

Keep only the listed columns (projection). Drops all other columns.

## Purpose

Reduces the table to a subset of columns. Useful for feature selection or before nodes that expect specific columns.

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | in        | table  | `table` — input data           |
|              | in        | list   | `columns` — column names to keep |
| **Outputs**  | out       | float  | `row_count`                    |
|              | out       | table  | `table` — same rows, fewer columns |
| **Params**   | config    | —      | `columns` (list or comma-sep string) |

## Example

**Input:** `{"table": [{"a": 1, "b": 2, "c": 3}], "columns": ["a", "c"]}`  
**Output:** table with only keys `a` and `c`.
