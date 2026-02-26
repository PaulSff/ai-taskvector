# MinMaxScaler

Scale numeric columns to [0, 1] (sklearn `MinMaxScaler`). Fit on first run, then transform.

## Purpose

Maps numeric features to the 0–1 range. Useful for neural networks or when bounds matter. Fitter stored in state.

## Interface

| Port / Param | Direction | Type   | Description        |
|--------------|-----------|--------|--------------------|
| **Inputs**   | in        | table  | `table` — input    |
| **Outputs**  | out       | float  | `row_count`        |
|              | out       | table  | `table` — scaled   |

## Example

**Input:** numeric columns with min/max varying  
**Output:** same rows with values in [0, 1].
