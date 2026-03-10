# RagSearch unit

Canonical unit: runs RAG index search. Output is a table of results for Filter / FormatRagPrompt.

- **Input:** `query` (str) — search query (e.g. user message). Optional when `edits` is used.
- **Input:** `edits` (Any) — optional. When present (list of action dicts), the first edit with `action: "search"` is used: `what`/`query`/`q` → query, `max_results` (1–50) → top_k. Connects from ProcessAgent (parser) for a second instance that runs the LLM’s search action.
- **Output:** `table` (list of `{text, metadata, score}`) — raw search results.
- **Params (from graph only; no fallbacks):** `persist_dir`, `embedding_model`, `top_k`, `content_type`.

Flow: first instance **inject_user_message → RagSearch (query) → Filter → FormatRagPrompt → Merge**. Second instance **parser (edits) → RagSearch (edits)** so the search action from the LLM runs in the same unit type; output `rag_search_action.table` for follow-up.
