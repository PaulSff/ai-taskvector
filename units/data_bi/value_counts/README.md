# ValueCounts

Count occurrences of each value in a column (pandas `value_counts`). Output table has column + count.

## Purpose

Produces a small table: one row per distinct value in the chosen column, with a count. Useful for histograms and categorical summaries.

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | in        | table  | `table` — input data           |
|              | in        | str    | `column` — column to count     |
| **Outputs**  | out       | float  | `row_count`                    |
|              | out       | table  | `table` — (value, count) rows  |

## Example

**Input:** `{"table": [...], "column": "status"}`  
**Output:** table with columns `status`, `count` — one row per status value.
