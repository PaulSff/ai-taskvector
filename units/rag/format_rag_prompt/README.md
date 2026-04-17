# FormatRagPrompt unit

Canonical unit that turns a **table of RAG results** (list of `{text, metadata, score}`) into the formatted "Relevant context from knowledge base" block for the prompt.

- **Input:** `table` (list of dicts from RagSearch → Filter).
- **Output:** `data` (str) — the block to inject as `rag_context` in Aggregate/Prompt.
- **Params:** `max_chars` and `snippet_max` — each may be:
  - an **integer** (or numeric string), or
  - a **param ref** string resolved by `units.canonical.app_settings_param`: `settings.<key>` (`config/app_settings.json`), `tool.<id>.<dotted.path>` (`assistants/tools/<id>/tool.yaml`), or `role.<id>.<dotted.path>` (`assistants/roles/<id>/role.yaml`). RAG defaults use `tool.rag_search.rag.*`; read_file overrides use `tool.read_file.rag.*`.

If either value is missing, invalid, or an unresolved `settings.*` ref, the unit outputs an empty string. Flow: **RagSearch → Filter (data_bi) → FormatRagPrompt → Aggregate** (rag_context key).
