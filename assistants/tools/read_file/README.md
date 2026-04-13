# `read_file` tool

Read indexed file content from the knowledge base: RAG path for normal files, or a dedicated subflow for `.xlsx`.

## Parser action

See `prompt.py` for `read_file` with `path` (and related fields).

## `tool.yaml`

- **`workflow`**: `read_file_workflow.json` — Router on path suffix; non-xlsx branch runs nested `rag_context_workflow.json` with path-based retrieval.
- **`rag`**: `max_chars`, `snippet_max` — `tool.read_file.rag.*` for nested format caps.

## Follow-up

`run_read_file_follow_up` in `__init__.py` → `TOOL_RUNNERS["read_file"]` in `registry.py`.
