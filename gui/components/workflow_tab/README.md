# Workflow tab (`workflow_tab`)

Flet UI for editing and running **process graphs**: draggable canvas, graph/code views, import/export, toolbar actions, and a bottom **run console**. The tab is wired into the desktop app from `gui/main.py` via `build_workflow_tab`.

## Public API

Import from the package root for the tab shell and canvas styling:

```python
from gui.components.workflow_tab import build_workflow_tab, get_default_style_config, GraphStyleConfig
```

- **`build_workflow_tab`** — defined in `workflow_tab.py`; builds the full tab column (canvas, toggles, dialogs hooks, run console).
- **Style exports** — `GraphStyleConfig`, `NodeStyle`, `LinkStyle`, and related constants come from `editor.graph_visual_editor`.

GUI code that must avoid importing `core.schemas` directly can use `process_graph.ProcessGraph` from `gui.components.workflow_tab.process_graph`.

## Package layout

| Path | Role |
|------|------|
| **`workflow_tab.py`** | Tab composition: toolbar, canvas vs code editor, console integration. |
| **`editor/`** | Graph canvas (`graph_visual_editor/`) and JSON/graph code editor (`graph_code_editor/`). |
| **`dialogs/`** | Add/remove nodes and links, import/export, save, view graph code. |
| **`console/`** | Bottom run console UI and helpers (`run_console.py`). |
| **`workflows/`** | Packaged JSON workflows plus runners; see below. |
| **`services/`** | Tab-local helpers (e.g. `units_library_types` for the Add Node dialog). |
| **`workflows/import_workflows/`** | JSON graphs for import flows (auto-detect / format-specific); loaded by `dialogs/dialog_import_workflow.py`. |
| **`process_graph.py`** | Thin re-export of `ProcessGraph` for boundary-friendly imports. |

## Workflows

Runnable graphs and their Python entry points live under **`workflows/`**:

- **`workflows.core_workflows`** — single-unit workflows (summary, diff, load, export, normalize, apply edits, etc.); implementation in `workflows/core_workflows/__init__.py` next to the JSON files.
- **`workflows.edit_workflows`** — one JSON workflow per graph-edit action; `runner.apply_edit_via_workflow` applies assistant edits.
- **`workflows.assistants_workflows`** — chat-oriented helpers (e.g. clean text, units library paths).
- **`workflows/import_workflows/`** — JSON only (`auto_import_workflow`, `import_workflow`, `new_flow_template`); paths are resolved in `dialogs/dialog_import_workflow.py`.

For a folder-by-folder breakdown of JSON files, see **[`workflows/README.md`](workflows/README.md)**.

## Related docs

- **`console/README.md`** — how the run console connects to `core_workflows` and the tab shell.
- **`editor/graph_visual_editor/README.md`**, **`editor/graph_code_editor/README.md`** — canvas and code editor internals.
- **`workflows/edit_workflows/README.md`** — edit-action resolution and tool-delegated workflows.

Higher-level behavior (Core vs GUI, units) is summarized in **`core/README.md`** at the repo root where it discusses `gui.components.workflow_tab.workflows.core_workflows`.
