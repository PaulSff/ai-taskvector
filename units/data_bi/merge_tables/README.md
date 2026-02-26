# MergeTables

Join two tables (pandas `merge`). Supports inner, left, right, outer via `how`.

## Purpose

Combines two tables on a key column (or list of columns). Useful for joining dimensions with facts or combining datasets.

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | in        | table  | `left` — left table            |
|              | in        | table  | `right` — right table          |
|              | in        | str    | `on` — key column(s)           |
|              | in        | str    | `how` — inner, left, right, outer |
| **Outputs**  | out       | float  | `row_count`                    |
|              | out       | table  | `table` — merged result        |

## Example

**Input:** `{"left": [...], "right": [...], "on": "id", "how": "inner"}`  
**Output:** table with rows where `id` exists in both tables.
