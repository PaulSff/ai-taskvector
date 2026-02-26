# StandardScaler

Standardize numeric columns to zero mean and unit variance (sklearn `StandardScaler`). Fit on first run, then transform.

## Purpose

Scales numeric features for ML. First step fits the scaler on the input table; subsequent steps transform using the fitted scaler (stored in state).

## Interface

| Port / Param | Direction | Type   | Description        |
|--------------|-----------|--------|--------------------|
| **Inputs**   | in        | table  | `table` — input    |
| **Outputs**  | out       | float  | `row_count`        |
|              | out       | table  | `table` — scaled numeric columns |

## Example

**Input:** table with numeric columns  
**Output:** same table with numeric columns transformed to (x - mean) / std.
