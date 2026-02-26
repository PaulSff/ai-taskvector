# RandomForestClassifier

Classification with random forest (sklearn `RandomForestClassifier`). Fit on first run.

## Purpose

Trains a random forest on numeric features with a target column. Adds `_pred` to the table. Model stored in state. Params: `n_estimators` (default 100).

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | in        | table  | `table` — features + target    |
|              | in        | str    | `target_column`                |
| **Outputs**  | out       | float  | `row_count`                    |
|              | out       | table  | `table` + `_pred`              |
|              | out       | float  | `accuracy`                     |
|              | out       | list   | `predictions`                  |
| **Params**   | config    | —      | `target_column`, `n_estimators`|

## Example

**Input:** table with numeric columns and `class` column  
**Output:** table with `_pred`; `accuracy` and `predictions` on output ports.
