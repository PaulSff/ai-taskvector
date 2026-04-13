# RagUpdate unit

Canonical unit that runs the RAG index incremental update (units_dir + mydata_dir) via `rag.context_updater.run_update`.

- **Params:** `rag_index_data_dir`, `units_dir`, `mydata_dir`, `embedding_model` (optional). Use **`settings.rag_index_data_dir`**, **`settings.mydata_dir`**, **`settings.rag_embedding_model`** in workflow JSON (resolved by `GraphExecutor` via `app_settings_param`). Relative directory strings are still normalized under the **repository root** inside the unit (so `units` → `<repo>/units`).
- **Inputs:** None.
- **Output:** `data` (dict) with keys `ok`, `need_index`, `units_count`, `mydata_count`, `error`, `message`, `details`.

Workflows (e.g. `rag/workflows/rag_update.json`) can trigger index updates; the GUI runs this workflow at startup instead of calling `run_update` directly.
