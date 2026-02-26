# LinearRegression

Linear regression (sklearn `LinearRegression`). Fit on first run; outputs predictions, MSE, and R².

## Purpose

Trains a linear model on numeric features with a target column. Adds `_pred` to the table. Model stored in state.

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | in        | table  | `table` — features + target    |
|              | in        | str    | `target_column`                |
| **Outputs**  | out       | float  | `row_count`                    |
|              | out       | table  | `table` + `_pred`              |
|              | out       | float  | `mse`, `r2`                    |
|              | out       | list   | `predictions`                  |

## Example

**Input:** table with numeric features and `y` column  
**Output:** table with `_pred`; `mse`, `r2`, `predictions` on output ports.
