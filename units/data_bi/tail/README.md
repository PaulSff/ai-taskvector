# Tail

Last n rows of the table (pandas `tail`).

## Purpose

Returns the last `n` rows. Useful for inspecting the end of a dataset.

## Interface

| Port / Param | Direction | Type   | Description        |
|--------------|-----------|--------|--------------------|
| **Inputs**   | in        | table  | `table` — input    |
|              | in        | int    | `n` — number of rows |
| **Outputs**  | out       | float  | `row_count`        |
|              | out       | table  | `table` — last n rows |

## Example

**Input:** `{"table": [...100 rows...], "n": 5}`  
**Output:** table with 5 rows (last 5 of the 100).
