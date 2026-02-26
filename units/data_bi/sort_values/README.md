# SortValues

Sort table by one or more columns (pandas `sort_values`). Ascending or descending.

## Purpose

Reorders rows by the given column(s). Use before Head/TopK to get "top N by column".

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | in        | table  | `table` — input data           |
|              | in        | str    | `by` — column(s) to sort by     |
|              | in        | bool   | `ascending` — default true      |
| **Outputs**  | out       | float  | `row_count`                     |
|              | out       | table  | `table` — sorted rows           |

## Example

**Input:** `{"table": [...], "by": "score", "ascending": false}`  
**Output:** table sorted by `score` descending.
