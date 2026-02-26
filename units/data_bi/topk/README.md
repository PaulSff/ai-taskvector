# TopK

Take the first K rows (same idea as Head). Often used after sorting to get "top K by some column".

## Purpose

Returns the first `k` rows. Can be wired with a dynamic `k` (e.g. from another node or agent).

## Interface

| Port / Param | Direction | Type   | Description        |
|--------------|-----------|--------|--------------------|
| **Inputs**   | in        | table  | `table` — input    |
|              | in        | int    | `k` — number of rows |
| **Outputs**  | out       | float  | `row_count`        |
|              | out       | table  | `table` — first k rows |
| **Params**   | config    | —      | `k` (default 10)   |

## Example

**Input:** `{"table": [...], "k": 3}`  
**Output:** table with 3 rows.
