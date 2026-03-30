# FormatRagPrompt unit

Canonical unit that turns a **table of RAG results** (list of `{text, metadata, score}`) into the formatted "Relevant context from knowledge base" block for the prompt.

- **Input:** `table` (list of dicts from RagSearch → Filter).
- **Output:** `data` (str) — the block to inject as `rag_context` in Aggregate/Prompt.
- **Params (from graph only; no fallbacks):**
  - `max_chars` (int): maximum total characters in the formatted block. Set in the graph (e.g. 1200).
  - `snippet_max` (int): maximum characters per result snippet. Set in the graph (e.g. 400).

If either param is missing or invalid, the unit outputs empty string. Flow: **RagSearch → Filter (data_bi) → FormatRagPrompt → Aggregate** (rag_context key).
