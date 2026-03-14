# Report unit

Writes a report file from the **ProcessAgent** parsed action `report`.

**Flow:** LLMAgent produces response → ProcessAgent parses it → parser output may contain `report` with `text` and `output_format`. This unit uses only **`text`** and **`output_format`** from the payload (and **`output_dir`** from unit params). It renders `text` to Markdown or CSV and writes `output_dir/report.md` or `output_dir/report.csv`. No LLM call.

**Input:** `parser_output` (dict from ProcessAgent, e.g. merge_response key or parser edits output).

**Params:** `output_dir` (required).

**Output:** `data` with `ok`, `output_path`, `error`, `report_preview`.

**Action schema (for LLM prompt):** Report is a regular extra action in the workflow designer list (Extra actions in `assistants/prompts.py`). Output `action: "report"` with `output_format` and `text`. The unit only writes the file. Only **`text`** and **`output_format`** are used. MD: `text` = `{ "title", "summary", "sections": [ { "heading", "body" } ] }`. CSV: `text` = `{ "headers": [...], "rows": [ [...] ] }`.
