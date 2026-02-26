# Describe

Numeric summary statistics (pandas `describe`: count, mean, std, min, quartiles, max).

## Purpose

Computes summary stats over numeric columns of the input table. Useful for EDA and feature understanding in data/BI flows.

## Interface

| Port / Param | Direction | Type   | Description        |
|--------------|-----------|--------|--------------------|
| **Inputs**   | in        | table  | `table` — input data |
| **Outputs**  | out       | float  | `row_count`        |
|              | out       | table  | `table` — describe result (index + stats) |

## Example

**Input (table):** rows with columns `["a", "b", "c"]`

**Output (table):** stats rows (count, mean, std, min, 25%, 50%, 75%, max) with index labeling the statistic.
