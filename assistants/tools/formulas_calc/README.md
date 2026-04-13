# `formulas_calc` tool

Recalculate an `.xlsx` workbook with the `formulas` library and read named output cells/ranges (Excel-style keys).

## Parser action

See `prompt.py` for `path`, `inputs`, `outputs`, and `output-format`. Parsed in `action_blocks.py` and executed by the `FormulasCalc` unit in the analyst workflow.

## `tool.yaml`

- **`workflow`**: `formulas_calc_workflow.json` — default inject + FormulasCalc graph for paths resolved via `get_tool_workflow_path("formulas_calc")`.

## Follow-up

`run_formulas_calc_follow_up` in `__init__.py` → `TOOL_RUNNERS["formulas_calc"]` in `registry.py`. Listed on **Analyst** (`ORDERED_ANALYST_TOOLS`); not on Workflow Designer follow-up order in `catalog.py`.
