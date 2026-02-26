# Head

First n rows of the table (pandas `head`).

## Purpose

Returns the first `n` rows. Useful for preview or limiting downstream flow size.

## Interface

| Port / Param | Direction | Type   | Description        |
|--------------|-----------|--------|--------------------|
| **Inputs**   | in        | table  | `table` — input    |
|              | in        | int    | `n` — number of rows (default 10) |
| **Outputs**  | out       | float  | `row_count`        |
|              | out       | table  | `table` — first n rows |
| **Params**   | config    | —      | `n` or `k`         |

## Example

**Input:** `{"table": [...100 rows...], "n": 5}`  
**Output:** table with 5 rows (first 5 of the 100).
