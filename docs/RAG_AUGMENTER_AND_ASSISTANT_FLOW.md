# RAG and assistant flow

## Current behavior

- **Workflow Designer** gets RAG context from the **RAG context workflow** (`get_rag_context(text, "Workflow Designer")`), which runs `rag_context_workflow.json` (rag_search → rag_filter → format_rag). The assistant sees workflows/nodes/docs relevant to the query and the hint: "Use file_path, raw_json_path, or id from above for import_workflow / import_unit when applicable."
- The assistant is **not** given the Units API / UnitSpec format in its system prompt in depth; it relies on the graph summary and on RAG snippets. The graph summary includes each unit's `input_ports` and `output_ports` **from the graph** (set from the registry on add_unit, or enriched from the registry when normalizing imported units with empty ports).
- **Unit-doc augmenter removed.** Unit docs are no longer generated automatically after `import_workflow`. Report generation from RAG content is handled by the **CreateFileOnRag** canonical unit: the assistant can emit a `create_file_on_rag` action (parsed by ProcessAgent); the CreateFileOnRag unit consumes the parsed payload and writes report.md or report.csv. LLM and parsing are done by LLMAgent and ProcessAgent in the workflow.

## CreateFileOnRag

- **Flow:** LLMAgent → ProcessAgent parses response → parser_output may contain `create_file_on_rag` with `path`, `prompt`, `output_format`, and `report` (JSON). The **CreateFileOnRag** unit reads this payload, renders `report` to Markdown or CSV, and writes to `output_dir/report.md` or `report.csv`.
- Report schema for the LLM is documented in `assistants/prompts.py` (RAG_ANALYZE_MD_JSON_SCHEMA, RAG_ANALYZE_CSV_JSON_SCHEMA, RAG_ANALYZE_SYSTEM). Wire CreateFileOnRag in the assistant workflow when this behavior is desired.

## Optional: improve “Units API” awareness in the prompt

- Add a **concise** Units API / UnitSpec summary to the Workflow Designer system prompt (e.g. port ordering, `observation_source_ids` / `action_target_ids`, and that unit docs in the knowledge base provide `input_ports` / `output_ports`). That way the assistant knows the *shape* of the API even when RAG hasn’t returned a specific unit yet.
- Keep detailed UnitSpec and wiring examples in RAG and in the “Relevant context from knowledge base” block.
