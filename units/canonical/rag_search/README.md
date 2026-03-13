# RagSearch unit

Canonical unit: runs RAG index search. Output is a table of results for Filter / FormatRagPrompt.

- **Input:** `query` (str) — search query (e.g. user message). Optional when `edits` is used.
- **Input:** `edits` (Any) — optional. When present (list of action dicts), the first edit with `action: "search"` is used: `what`/`query`/`q` → query, `max_results` (1–50) → top_k.
- **Output:** `table` (list of `{text, metadata, score}`) — raw search results.
- **Params:** `persist_dir`, `embedding_model`, `top_k`, `content_type`, `ignore` (optional). When `ignore` is true, the unit returns an empty table without querying the index (used on follow-up runs where RAG context is injected via `follow_up_context` so there is no double RAG).

In the assistant workflow: **inject_user_message → RagSearch (query) → Filter → FormatRagPrompt → Aggregate** (rag_context). On-demand RAG (when the LLM returns `action: "search"`) is handled in the GUI: chat runs `get_rag_context()` and re-runs the workflow with `inject_follow_up_context`.
