# FilterRows

Filter rows by pandas `query` expression or by column + operator + value.

## Purpose

Same semantics as Filter but supports an optional pandas `query` string (e.g. `"a > 1 and b < 2"`). When no query is set, uses column/op/value like Filter.

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | in        | float  | `value` — threshold            |
|              | in        | table  | `table` — input data           |
|              | in        | str    | `query` — pandas query expr    |
|              | in        | str    | `column`, `op`                 |
| **Outputs**  | out       | float  | `row_count`                    |
|              | out       | table  | `table` — filtered rows        |

## Example

**Input (query):** `{"table": df, "query": "score >= 0.5"}`  
**Output:** table with rows where `score >= 0.5`.
