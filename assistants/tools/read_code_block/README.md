# `read_code_block` tool

Request source code for a **code block** attached to a graph unit when the lightweight summary is not enough.

## Parser action

See `prompt.py`. Parser emits `read_code_block` with a unit/block id; follow-up may run nested RAG per implementation path.

## `tool.yaml`

- **`workflow`**: `read_code_block_follow_up_workflow.json` — normalize/validate → lookup → Router → nested `rag_context_workflow` for paths.
- **`rag`**: `max_chars`, `snippet_max` — nested `format_rag` overrides (`tool.read_code_block.rag.*`).

## Follow-up

`run_read_code_block_follow_up` in `__init__.py` → `TOOL_RUNNERS["read_code_block"]` in `registry.py`. Workflow Designer order includes this tool; Analyst omits it.
