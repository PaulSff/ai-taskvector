# GroupByAgg

Group table by column(s) and aggregate (pandas `groupby`). Supports `size`, `sum`, `mean`, etc.

## Purpose

Groups rows by the given column(s) and applies an aggregation (e.g. count, sum, mean) on numeric columns. Output is a table with one row per group.

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | in        | table  | `table` — input data           |
|              | in        | str    | `by` — column(s) to group by   |
|              | in        | str    | `agg` — "size", "sum", "mean", etc. |
| **Outputs**  | out       | float  | `row_count`                    |
|              | out       | table  | `table` — grouped result       |

## Example

**Input:** `{"table": [...], "by": "category", "agg": "size"}`  
**Output:** table with columns `category`, `count` (one row per category).
