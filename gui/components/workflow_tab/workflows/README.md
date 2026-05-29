# Workflow JSON layout

Workflow definitions (`.json` DAGs) for the tab live under **`gui/components/workflow_tab/workflows/`**, grouped by purpose (RAG helper graphs additionally live under **`rag/workflows/`** at repo root):

| Folder | Purpose | Examples |
|--------|---------|----------|
| **workflows/core_workflows/** | Single-unit workflows and their Python runner (`workflows/core_workflows/__init__.py`: graph summary, diff, load, export, runtime label, normalize, apply edits). GUI reaches Core only via these. | `graph_summary_single.json`, `load_workflow_single.json`, `apply_edits_single.json` |
| **workflows/edit_workflows/** | One workflow per graph-edit action (add_unit, connect, disconnect, etc.). Used by the edit runner when applying agent edits. **add_comment** and **todo_list** edit graphs are loaded from `agents/tools/add_comment/` and `agents/tools/todo_manager/` via `tool.yaml`. | `edit_add_unit.json`, `edit_connect.json`, … |
| **workflows/agents_workflows/** | Chat/agent helpers: units library, etc. Client todo injection graph lives under `agents/tools/todo_manager/` (`tool.yaml` + `todo_list.json`). RAG context: `agents/tools/rag_search/`. RAG index/doc graphs: **`rag/workflows/`** (`rag_update.json`, `doc_to_text.json`). | `units_library_workflow.json` |
| **tools/** | *(empty by default.)* agent-invoked runner graphs (including RL training) live under `agents/tools/<id>/` via `tool.yaml`. | — |
| **workflows/import_workflows/** | Import dialogs: auto-detect origin or import with a given format. | `auto_import_workflow.json`, `import_workflow.json` |
| *(tab root)* | Other tab-local assets only; Run/grep and WD web tools use `agents/tools/<id>/tool.yaml` + JSON next to it. | — |

Most paths used in code (e.g. `workflows.core_workflows` package, `gui/chat/context/todo_list_manager.py`) point into these folders; RAG index/doc helper graphs live under **`rag/workflows/`** (see `rag_update_workflow_path` / `doc_to_text_workflow_path` in **`rag/ragconf.yaml`**).
