# RagSearch unit

Canonical unit: runs RAG index search. Output is a table of results for Filter / FormatRagPrompt.

- **Input:** `query` (str) — search query (e.g. user message). Optional when `edits` or `file_path` is used.
- **Input:** `edits` (Any) — optional. When present (list of action dicts), the first edit with `action: "search"` is used: `what`/`query`/`q` → query, `max_results` (1–50) → top_k. Optional `max_chars` and `snippet_max` are passed through to FormatRagPrompt (see below).
- **Input:** `file_path` (str) — optional. When set, retrieves all indexed chunks for that file path (path-based retrieval) with expanded max_chars/snippet_max so the assistant gets full content from the index.
- **Output:** `table` (list of `{text, metadata, score}`) — raw search results.
- **Params:** `persist_dir`, `embedding_model`, `top_k`, `content_type`, `ignore` (optional). In workflow JSON use **`settings.rag_index_data_dir`** and **`settings.rag_embedding_model`** (resolved by `GraphExecutor` via `app_settings_param`, merging `rag/ragconf.yaml`). When `ignore` is true, the unit returns an empty table without querying the index (used on follow-up runs where RAG context is injected via `follow_up_context` so there is no double RAG).

**Per-chunk and total size:** RagSearch does not truncate; the **FormatRagPrompt** unit (downstream) does. Set **`max_chars`** / **`snippet_max`** to integers or strings **`settings.<app_settings key>`** in the graph (or in `unit_param_overrides` on nested `RunWorkflow`).

The bundled RAG context graph JSON is **`assistants/tools/rag_search/rag_context_workflow.json`**, registered in **`assistants/tools/rag_search/tool.yaml`** ``workflow``. Chat resolves it via `get_rag_context_workflow_path()` → `assistants.tools.workflow_path.get_tool_workflow_path("rag_search")`.

In the assistant workflow: **inject_user_message → RagSearch (query) → Filter → FormatRagPrompt → Aggregate** (rag_context). On-demand RAG (when the LLM returns `action: "search"`) is handled in the GUI: chat runs `get_rag_context()` and re-runs the workflow with `inject_follow_up_context`.
