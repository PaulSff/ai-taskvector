# TrainTestSplit

Split table into train and test sets (sklearn `train_test_split`). Outputs train table, test table, and row count.

## Purpose

Randomly splits the input table into train and test subsets. Used before fitting models. Ratio controlled by `test_size` (default 0.2). State holds the split for downstream nodes.

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | in        | table  | `table` — input data           |
|              | in        | float  | `test_size` — fraction for test (0–1) |
| **Outputs**  | out       | float  | `row_count`                    |
|              | out       | table  | `table` — train rows           |
|              | out       | table  | `train` — same as table        |
|              | out       | table  | `test` — test rows             |
| **Params**   | config    | —      | `test_size`, `random_state`    |

## Example

**Input:** `{"table": [...100 rows...], "test_size": 0.2}`  
**Output:** `table`/`train` = 80 rows, `test` = 20 rows (via separate port or state).
