# Core

The **core** package holds the canonical data model, graph editing, normalization, and environment construction. It is the single source of truth for process graphs and training configs. **Callers (GUI, runners, agents) are encouraged to reach Core only through workflows and canonical units**, so that all business logic runs in one place and stays testable.

## Contents

| Area | Role |
|------|------|
| **`core.schemas`** | Canonical structures: `ProcessGraph`, `Unit`, `Connection`, `CodeBlock`, `TodoList`, training config, etc. Single source of truth for the rest of the stack. |
| **`core.graph`** | Graph editing and analysis: apply edits, batch apply, summary, diff, import resolution, todo list. |
| **`core.normalizer`** | Format conversion: raw input (dict, YAML, Node-RED, n8n, PyFlow, etc.) → `ProcessGraph`; `ProcessGraph` → export formats; runtime detection. |
| **`core.env_factory`** | Build a Gymnasium env from a process graph and goal config (for RL training). |

## Interaction through units

The GUI and other high-level code **do not call Core directly** (except for schema types like `ProcessGraph`). Instead they:

1. Run **workflows** (JSON DAGs) that contain **canonical units**.
2. Those units, when executed by the runtime, **call Core** and expose results on their output ports.

So Core is used **only** by:

- The **runtime** (executing units),
- **Canonical units** (whose `step_fn` or graph-edit logic imports `core.graph`, `core.normalizer`, etc.).

This keeps a clear boundary: Core is the engine; units are the API.

### Units that use Core

| Unit | Core usage |
|------|------------|
| **GraphSummary** | `core.graph.summary.graph_summary` — LLM-friendly summary of the graph. |
| **GraphDiff** | `core.graph.diff.graph_diff` — compact diff between two graphs. |
| **ApplyEdits** | `core.graph.batch_edits.apply_workflow_edits` — apply a list of graph edits; uses `core.graph.summary.graph_summary` for content-for-display. |
| **add_unit / connect / …** (graph_edit) | `core.graph.graph_edits.apply_graph_edit` — apply a single edit (add_unit, connect, add_code_block, etc.). |
| **todo_list** | `core.graph.todo_list` — add/remove tasks, mark completed, manage todo list metadata on the graph. |
| **Import_workflow** | `core.graph.import_resolver.load_workflow_to_canonical`, `core.normalizer.to_process_graph` — load and merge an external workflow into the current graph. |
| **LoadWorkflow** | `core.normalizer.load_process_graph_from_file` — load a process graph from a file path. |
| **ExportWorkflow** | `core.normalizer.to_process_graph`, `core.normalizer.export.from_process_graph` — export the graph to Node-RED / PyFlow / n8n / ComfyUI. |
| **RuntimeLabel** | `core.normalizer.runtime_detector.runtime_label`, `is_canonical_runtime` — detect runtime type (canonical, node_red, n8n, etc.) and native flag. |
| **NormalizeGraph** | `core.normalizer.to_process_graph` — normalize a raw graph dict to canonical and output as dict. |
| **RunWorkflow** | `core.normalizer.load_process_graph_from_file`, `to_process_graph` — load/validate graph; execution is via `runtime.executor.GraphExecutor`. |
| **UnitsLibrary** | `core.normalizer.runtime_detector.is_external_runtime` — decide which unit catalog to show. |

The GUI uses **`gui/components/workflow_tab/core_workflows/`** (Python package `gui.components.workflow_tab.core_workflows`, JSON + runner in one tree) to run small single-purpose workflows (e.g. `graph_summary_single.json`, `load_workflow_single.json`) that call these units. So loading, exporting, runtime detection, summary, diff, and normalization are all done **via workflows**, not by importing Core from the GUI.

## Main entry points

- **Normalization (in/out)**  
  - `core.normalizer.to_process_graph(raw, format)` — normalize to `ProcessGraph`.  
  - `core.normalizer.load_process_graph_from_file(path, format)` — load from file (uses `to_process_graph`).  
  - `core.normalizer.export.from_process_graph(graph, format)` — export to Node-RED / PyFlow / n8n / ComfyUI.

- **Graph editing**  
  - `core.graph.graph_edits.apply_graph_edit` — apply one edit.  
  - `core.graph.batch_edits.apply_workflow_edits` — apply a list of edits (used by the ApplyEdits unit).

- **Graph analysis**  
  - `core.graph.summary.graph_summary` — LLM-friendly summary (units, connections, code blocks, todos, etc.).  
  - `core.graph.diff.graph_diff` — text diff between two graphs.

- **Runtime detection**  
  - `core.normalizer.runtime_detector.runtime_label(graph)` — e.g. `"canonical"`, `"node_red"`, `"n8n"`.  
  - `core.normalizer.runtime_detector.is_canonical_runtime(graph)` — True if native/canonical.

- **Environment**  
  - `core.env_factory.build_env(process_graph, goal)` — build Gymnasium env for RL.

All of these are consumed by the units listed above; high-level code should go through those units and their workflows rather than calling Core directly.
