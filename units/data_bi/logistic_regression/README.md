# LogisticRegression

Binary/multiclass classification (sklearn `LogisticRegression`). Fit on first run; outputs predictions and accuracy.

## Purpose

Trains logistic regression on numeric features with a target column. Adds `_pred` and `_proba` (binary case) to the table. Model stored in state for reuse.

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | in        | table  | `table` — features + target    |
|              | in        | str    | `target_column` — target name  |
| **Outputs**  | out       | float  | `row_count`                    |
|              | out       | table  | `table` + `_pred`, `_proba`    |
|              | out       | float  | `accuracy`                     |
|              | out       | list   | `predictions`                  |
| **Params**   | config    | —      | `target_column`                |

## Example

**Input:** table with numeric columns and a `label` column  
**Params:** `{"target_column": "label"}`  
**Output:** table with `_pred`, `_proba`; `accuracy` and `predictions` on output ports.
