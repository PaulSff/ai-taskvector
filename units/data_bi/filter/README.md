# Filter

Filter rows by column, operator, and value (pandas-style boolean indexing). Can be wired as an action target (first input = value).

## Purpose

Keeps only rows where the given column satisfies the operator vs the value (lt, le, gt, ge, eq, neq). Useful for threshold-based filtering and for RL (agent sets `value` to control filter).

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | in        | float  | `value` — threshold (e.g. from agent) |
|              | in        | table  | `table` — input data           |
|              | in        | str    | `column` — column name         |
|              | in        | str    | `op` — lt, le, gt, ge, eq, neq |
| **Outputs**  | out       | float  | `row_count`                    |
|              | out       | table  | `table` — filtered rows        |
| **Params**   | config    | —      | `column`, `op`, `value`        |

## Example

**Input:** `{"table": [...], "column": "score", "op": "ge", "value": 0.5}`  
**Output:** rows where `score >= 0.5`.
