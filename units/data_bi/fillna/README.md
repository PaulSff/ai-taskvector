# FillNa

Fill missing (NaN/null) values with a constant (pandas `fillna`).

## Purpose

Replaces missing values in the table with a given value (e.g. 0, mean, or placeholder). Can be set via input port or params.

## Interface

| Port / Param | Direction | Type   | Description                |
|--------------|-----------|--------|----------------------------|
| **Inputs**   | in        | table  | `table` — input data       |
|              | in        | float  | `value` — fill value       |
| **Outputs**  | out       | float  | `row_count`                |
|              | out       | table  | `table` — with NaNs filled  |
| **Params**   | config    | —      | `value` — default fill     |

## Example

**Input:** `{"table": [{"a": 1, "b": None}, {"a": None, "b": 3}], "value": 0}`  
**Output:** table with None/NaN replaced by 0.
