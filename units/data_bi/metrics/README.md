# Metrics

Compute accuracy, F1, MSE, and R² from a table with `y_true` and `y_pred` columns (sklearn metrics).

## Purpose

Evaluates predictions: for classification (categorical or &lt;20 unique values) outputs accuracy and F1; for regression outputs MSE and R². Column names configurable via params (`y_true`, `y_pred`).

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | in        | table  | `table` — must have y_true and y_pred columns |
|              | in        | str    | `y_true`, `y_pred` — column names |
| **Outputs**  | out       | float  | `row_count`                    |
|              | out       | table  | `table` — pass-through         |
|              | out       | float  | `accuracy`, `f1`, `mse`, `r2`  |
| **Params**   | config    | —      | `y_true` (default "y_true"), `y_pred` (default "_pred") |

## Example

**Input:** table with columns `y_true`, `_pred` (from a classifier)  
**Output:** `{"accuracy": 0.92, "f1": 0.91, "mse": 0.0, "r2": 0.0}` (classification).

**Input:** table with numeric `y_true`, `_pred`  
**Output:** `{"accuracy": 0.0, "f1": 0.0, "mse": 0.05, "r2": 0.88}` (regression).
