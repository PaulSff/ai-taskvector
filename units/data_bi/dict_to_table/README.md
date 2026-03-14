# DictToTable

Convert a dictionary to a table (DataFrame / list of dicts) so it can flow through data_bi pipelines.

## Purpose

Pandas provides `pd.DataFrame(data)` and `pd.DataFrame([data])` to turn dicts into tables. This unit does that so upstream dict output (e.g. from an Aggregate/Gate) can be fed into FilterRows, GroupByAgg, etc.

- **Flat dict** → one row: `{"Name": "Alice", "Age": 25, "City": "NYC"}` → table with 1 row, columns Name, Age, City.
- **Dict of lists** → multiple rows: `{"Name": ["Alice","Bob"], "Age": [25,30]}` → table with 2 rows. Requires pandas.

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | data      | Any    | `data` — dict or list of dicts |
| **Outputs**  | row_count | float  | number of rows                 |
|              | table     | table  | resulting table                |

## Example

**Input (flat dict):** `{"data": {"runtime": "native", "coding_is_allowed": true}}`  
**Output:** table with 1 row, columns `runtime`, `coding_is_allowed`.

**Input (dict of lists):** `{"data": {"Name": ["Alice","Bob"], "Age": [25,30]}}`  
**Output:** table with 2 rows.
