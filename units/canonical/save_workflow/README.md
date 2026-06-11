# SaveWorkflow

SaveWorkflow unit: save a workflow graph to disk (versioned) in json or yaml.

## Purpose

Save a workflow graph as a timestamped, versioned file on disk. Writes a new file only when the current graph differs from the latest saved version (MD5 of canonical JSON). Supports json or yaml output and allows overriding the save-path template via params.


## Behavior

- Canonical JSON serialization orders keys (units, connections first) to produce stable bytes for hashing.
- Computes MD5 of the serialized bytes; if identical to the latest saved file (same extension), the unit returns error {"error":"no changes to save"} and does not write a new file.
- On successful save returns saved_at = "<resolved path>".
- If graph is None returns error {"error":"no workflow loaded"}.
- YAML output requires PyYAML (yaml.safe_dump); if unavailable, save fails with {"error":"save failed"}.

## Interface

| Port / Param            | Direction | Type                         | Description                                                                 |
|-------------------------|-----------|------------------------------|-----------------------------------------------------------------------------|
| **Inputs**              | graph     | ProcessGraph | dict | None | The workflow graph to save. If None, unit returns a "no workflow loaded" error. |
| **Outputs**             | saved_at  | str or None                  | On success: path string of the saved file. On failure: None.               |
|                         | error     | dict or None                 | On failure: {"error":"<reason>"} (e.g., "no changes to save", "no workflow loaded", "save failed"). |
| **Params**              | format    | str                          | "json" or "yaml" (default "json").                                         |
|                         | workflow_save_path | str               | Optional template override for the versioned save path.                    |
|                         | project_name | str                       | Optional explicit project name override (falls back to settings).          |
|                         | repo_root | str or Path                  | Optional repo root override (falls back to settings REPO_ROOT).           |

Template placeholders supported in workflow_save_path:
- $PROJECT_NAME$
- $YY-MM-DD-HHMMSS$

Default template is read from settings via get_workflow_save_path_template() when no workflow_save_path param is provided.

## Example

Params:
```json
{
  "format": "json",
  "workflow_save_path": "mydata/config/my_workflows/$PROJECT_NAME$/$PROJECT_NAME$_workflow_$YY-MM-DD-HHMMSS$.json",
  "project_name": "demo_project"
}
```

Input: 

```json
{"graph": { "environment_type": "thermodynamic", "units": [...], "connections": [...] }}
```

Possible Outputs:

- Success:
```json
{"saved_at": "mydata/config/my_workflows/demo_project/demo_project_workflow_26-06-11-153045.json", "error": null}
```

- No changes:
```json
{"saved_at": null, "error": {"error": "no changes to save"}}
```

- No graph:

```json
{"saved_at": null, "error": {"error": "no workflow loaded"}}
```
