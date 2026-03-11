# CreateFileOnRag unit

Writes a report file from the **ProcessAgent** parsed action `create_file_on_rag`.

**Flow:** LLMAgent produces response → ProcessAgent parses it → parser output may contain `create_file_on_rag`: `{ "path": [...], "prompt": "...", "output_format": "md" | "csv", "report": { ... } }`. This unit reads `parser_output["create_file_on_rag"]`, renders `report` to Markdown or CSV, and writes `output_dir/report.md` or `output_dir/report.csv`. No LLM call.

**Input:** `parser_output` (dict from ProcessAgent, e.g. merge_response key or parser edits output).

**Params:** `output_dir` (required).

**Output:** `data` with `ok`, `output_path`, `error`, `report_preview`.

**Action schema (for LLM prompt):** The LLM should output a JSON block with `action: "create_file_on_rag"`, plus `path`, `prompt`, `output_format`, and `report`. For MD: `report` = `{ "title", "summary", "sections": [ { "heading", "body" } ] }`. For CSV: `report` = `{ "headers": [...], "rows": [ [...] ] }`. See `assistants/prompts.py` (RAG_ANALYZE_MD_JSON_SCHEMA / RAG_ANALYZE_CSV_JSON_SCHEMA) for the exact schema.
