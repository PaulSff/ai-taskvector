# RagUpdate unit

Canonical unit that runs the RAG index incremental update (units_dir + mydata_dir) via `rag.context_updater.run_update`.

- **Params:** `rag_index_data_dir`, `units_dir`, `mydata_dir`, `embedding_model` (optional).
- **Inputs:** None.
- **Output:** `data` (dict) with keys `ok`, `need_index`, `units_count`, `mydata_count`, `error`, `message`, `details`.

Workflows (e.g. `gui/flet/components/workflow/assistants/rag_update.json`) can trigger index updates; the GUI runs this workflow at startup instead of calling `run_update` directly.
