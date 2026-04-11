# Workflow JSON layout

Workflow definitions (`.json` DAGs) under `gui/flet/components/workflow/` are grouped by purpose:

| Folder | Purpose | Examples |
|--------|---------|----------|
| **core/** | Single-unit workflows used by `core_workflows.py` (graph summary, diff, load, export, runtime label, normalize, apply edits). GUI reaches Core only via these. | `graph_summary_single.json`, `load_workflow_single.json`, `apply_edits_single.json` |
| **edit_workflows/** | One workflow per graph-edit action (add_unit, connect, disconnect, etc.). Used by the edit runner when applying assistant edits. | `edit_add_unit.json`, `edit_connect.json`, `edit_todo_list.json` |
| **assistants/** | Chat/assistant helpers: todo list, RAG context/update, doc-to-text, units library. | `todo_list.json`, `rag_context_workflow.json`, `rag_update.json`, `doc_to_text.json`, `units_library_workflow.json` |
| **tools/** | *(empty by default.)* Assistant-invoked runner graphs (including RL training) live under `assistants/tools/<id>/` via `tool.yaml`. | — |
| **import/** | Import dialogs: auto-detect origin or import with a given format. | `auto_import_workflow.json`, `import_workflow.json` |
| *(root)* | Other tab-local assets only; Run/grep and WD web tools use `assistants/tools/<id>/tool.yaml` + JSON next to it. | — |

All paths used in code (e.g. `core_workflows.py`, `todo_list_manager.py`, settings defaults) point into these folders.
