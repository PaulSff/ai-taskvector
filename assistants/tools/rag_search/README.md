# `rag_search` tool

Vector search over the project RAG index (workflows, docs, mydata, team members, etc.) and format hits for the prompt.

## Parser action

See `prompt.py` for `search` / query-style actions. Chat also injects RAG context by running the context workflow directly (same graph).

## `tool.yaml`

- **`workflow`**: `rag_context_workflow.json` — RagSearch → Filter (`score` column) → FormatRagPrompt.
- **`rag`**: `min_score`, `format_max_chars`, `snippet_max` — referenced from workflow JSON and nested `RunWorkflow` overrides as `tool.rag_search.rag.*` (see `units/canonical/app_settings_param.py`).

## Follow-up

`run_rag_search_follow_up` in `__init__.py` → `TOOL_RUNNERS["rag_search"]` in `registry.py`.
