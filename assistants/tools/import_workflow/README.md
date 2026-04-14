# `import_workflow` tool (graph edit)

Graph edit action that loads an external flow (path or URL + origin) and resolves to `replace_graph` / merge via `core.graph.import_resolver`. The **Import_workflow** canonical unit runs the conversion.

## `prompt.py`

`TOOL_ACTION_PROMPT_LINE` — inlined into Workflow Designer “Extra actions” via `{tool:import_workflow}`.

## `tool.yaml`

- **`workflow`**: repo-root path to the single-unit graph JSON (shared with `gui/components/workflow_tab/workflows/import_workflows/import_workflow.json`). Resolved with `assistants.tools.workflow_path.get_tool_workflow_path("import_workflow")`.
- **`id`**: `import_workflow` (stable tool id for path resolution).

## `follow_ups.py`

Post-apply assistant inject / user message (`IMPORT_POST_APPLY_*`) after canvas apply when the edit batch included `import_workflow`. Re-exported from `assistants.roles.workflow_designer.prompts` as `WORKFLOW_DESIGNER_IMPORT_*` for `config/prompts/workflow_designer.json` fragment keys.

There is **no** parser-output follow-up runner for this id (unlike `grep` / `rag_search`); it is not listed in `assistants/tools/catalog.py` `ORDERED_*`.
