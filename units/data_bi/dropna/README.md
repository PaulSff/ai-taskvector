# DropNa

Drop rows with missing (NaN/null) values. Optional subset of columns to consider (pandas `dropna`).

## Purpose

Cleans tables by removing rows that contain missing values. When `subset` is provided, only those columns are checked.

## Interface

| Port / Param | Direction | Type   | Description                          |
|--------------|-----------|--------|--------------------------------------|
| **Inputs**   | in        | table  | `table` — input data                  |
|              | in        | list   | `subset` — optional column names      |
| **Outputs**  | out       | float  | `row_count`                           |
|              | out       | table  | `table` — rows with NaNs dropped      |
| **Params**   | config    | —      | `subset` — optional list or comma-sep string |

## Example

**Input:** `{"table": [{"a": 1, "b": 2}, {"a": None, "b": 3}, {"a": 4, "b": None}]}`  
**Output (no subset):** table with only the first row (or all rows dropped if any NaN).

**Params:** `{"subset": ["a"]}` — drop only when `a` is missing.  
**Output:** two rows (first and third).
