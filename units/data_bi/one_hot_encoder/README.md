# OneHotEncoder

One-hot encode categorical columns (sklearn `OneHotEncoder`). Replaces categories with binary columns. Fit on first run.

## Purpose

Converts categorical (object/category) columns into numeric one-hot columns for ML. Unknown categories are ignored (handle_unknown="ignore"). Encoder stored in state.

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | in        | table  | `table` — input                |
|              | in        | list   | `columns` — columns to encode  |
| **Outputs**  | out       | float  | `row_count`                    |
|              | out       | table  | `table` — original non-cat + one-hot columns |
| **Params**   | config    | —      | `columns`                      |

## Example

**Input:** `{"table": [{"cat": "A"}, {"cat": "B"}], "columns": ["cat"]}`  
**Output:** table with columns like `cat_A`, `cat_B` (0/1).
