# TablesToText

Converts a list of tables to a single string. Each table is exported as CSV (default) or plain text via pandas. Used in document-to-text workflows (e.g. RAG indexing) so table content is compact and searchable.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**    | tables    | Any  | List of tables. Accepts two formats: 1. List of row dicts or DataFrame; 2. Each table is a dict `{"rows": [...], "schema": [...]}`. Cells may be dicts `{"value": , "formula": <str/null>}` |
| **Outputs**  | text      | str  | Concatenated string (tables separated by `\n\n`). |
| **Outputs**  | row_count | float| Total number of rows across all tables. |
| **Params**   | format    | str  | `"csv"` (default) or `"plain"` (DataFrame.to_string()). |

## Example

Input `tables = [ [{"A": 1, "B": 2}, {"A": 3, "B": 4}], [{"X": "a"}] ]`

or

`tables = [
[{"A": 1, "B": 2}, {"A": 3, "B": 4}],
{"rows": [{"X": {"value": "a", "formula": None}}], "schema": [{"index":0,"letter":"A","name":"X"}]}
]`

Output `text`: `"A,B\n1,2\n3,4\n\nX\na"` (CSV blocks joined by double newline).
