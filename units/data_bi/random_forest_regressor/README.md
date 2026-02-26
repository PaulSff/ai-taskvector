# RandomForestRegressor

Regression with random forest (sklearn `RandomForestRegressor`). Fit on first run.

## Purpose

Trains a random forest for regression on numeric features with a target column. Adds `_pred` to the table. Model stored in state. Params: `n_estimators` (default 100).

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | in        | table  | `table` — features + target    |
|              | in        | str    | `target_column`                |
| **Outputs**  | out       | float  | `row_count`                    |
|              | out       | table  | `table` + `_pred`              |
|              | out       | float  | `mse`, `r2`                    |
|              | out       | list   | `predictions`                  |
| **Params**   | config    | —      | `target_column`, `n_estimators`|

## Example

**Input:** table with numeric features and `y`  
**Output:** table with `_pred`; `mse`, `r2`, `predictions` on output ports.
