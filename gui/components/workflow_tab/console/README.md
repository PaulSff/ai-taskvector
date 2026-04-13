# Workflow run console (`workflow/console`)

Flet **bottom panel** on the Workflow tab: run the current graph via the **RunWorkflow** tool workflow, show structured output, optionally append a **grep** of the debug log. Chat can mirror the same output without re-running (`show_console_with_run_output`).

---

## Modules

| File | Role |
|------|------|
| **`console.py`** | `build_workflow_run_console`: collapsible console UI (`build_code_display`), **Run** button, async run + error aggregation + log grep, and `show_console_with_run_output` for chat. |
| **`run_console.py`** | Pure helpers: `format_run_outputs`, `debug_log_param_overrides_for_graph_dict` (keep Debug units on `get_debug_log_path()`), `build_initial_inputs_for_run`, `run_graph_sync` (in-process `GraphExecutor`). |
| **`__init__.py`** | Re-exports the public API below. |

---

## Imports

Prefer the package:

```python
from gui.components.workflow_tab.console import (
    build_workflow_run_console,
    format_run_outputs,
    debug_log_param_overrides_for_graph_dict,
)
```

Or submodules: `gui.components.workflow_tab.console.console`, `gui.components.workflow_tab.console.run_console`.

---

## Public API (summary)

- **`build_workflow_run_console(page, graph_ref, show_toast)`** → `WorkflowRunConsoleControls` with `console_container`, `run_button`, `show_console_with_run_output(run_output, *, append_log_grep=False)`.
- **`format_run_outputs(outputs)`** — executor-style dict → newline log text for the console.
- **`debug_log_param_overrides_for_graph_dict(graph_dict, log_path)`** — per–Debug-unit `log_path` overrides for RunWorkflow so console grep matches settings.
- **`build_initial_inputs_for_run(graph, user_message)`** — map non-empty message onto **Inject** units.
- **`run_graph_sync(graph, initial_inputs)`** — synchronous `GraphExecutor.execute` (register env-agnostic / data_bi / web units first); use from a worker thread if needed.

---

## Related

- **Small JSON workflows** (graph summary, diff, …): `gui.components.workflow_tab.core_workflows`.
- **Workflow tab shell**: `gui.components.workflow_tab.workflow.build_workflow_tab` wires the console into the toolbar column.
