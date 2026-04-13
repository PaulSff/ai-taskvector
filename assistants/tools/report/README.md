# `report` tool

Generate a structured report (Markdown or CSV) and write it under the role’s report output directory via the canonical `Report` unit.

## Parser action

See `prompt.py` for `report` action shape (`output_format`, `text` payload). Processed from `parser_output` in assistant workflows that include the Report unit.

## `tool.yaml`

This package has **no** `tool.yaml` — report paths and `output_dir` come from role YAML (`role.<id>.report.output_dir`) and graph params, not from a standalone workflow file here.

## Follow-up

`run_report_follow_up` in `__init__.py` → `TOOL_RUNNERS["report"]` in `registry.py`. Prompt fragments may be adjusted via `follow_up_fragment_overrides.py`.
