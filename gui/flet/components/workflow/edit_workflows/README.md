# Edit workflows (one workflow per edit type)

Small workflows that apply a **single** graph edit using the canonical graph_edit units (`units/canonical/graph_edit`). Each unit calls `core.graph.graph_edits.apply_graph_edit` via `_apply.apply_edit`. The GUI (or any runner) can apply an edit by running the matching workflow with the current graph and edit payload.

## Workflows

| Action            | File                     | Unit id         | unit_param_overrides (from `edit` dict) |
|-------------------|--------------------------|-----------------|----------------------------------------|
| add_unit          | edit_add_unit.json       | add_unit        | `{"unit": edit["unit"]}`               |
| add_pipeline      | edit_add_pipeline.json   | add_pipeline    | `{"pipeline": edit["pipeline"]}`       |
| remove_unit       | edit_remove_unit.json    | remove_unit     | `{"unit_id": edit["unit_id"]}`         |
| connect           | edit_connect.json       | connect         | `{"from_id": edit["from"], "to_id": edit["to"], "from_port": edit.get("from_port"), "to_port": edit.get("to_port")}` |
| disconnect        | edit_disconnect.json     | disconnect      | `{"from_id": edit["from"], "to_id": edit["to"], "from_port": edit.get("from_port"), "to_port": edit.get("to_port")}` |
| replace_unit      | edit_replace_unit.json   | replace_unit    | `{"find_unit": edit["find_unit"], "replace_with": edit["replace_with"]}` |
| replace_graph     | edit_replace_graph.json  | replace_graph   | `{"units": edit["units"], "connections": edit["connections"]}` |
| add_code_block    | edit_add_code_block.json | add_code_block  | `{"code_block": edit["code_block"]}`   |
| add_comment       | edit_add_comment.json    | add_comment     | `{"info": edit["info"], "commenter": edit.get("commenter")}` |
| add_environment   | edit_add_environment.json| add_environment | `{"env_id": edit["env_id"]}`           |
| no_edit           | edit_no_edit.json        | no_edit         | `{"reason": edit.get("reason")}`       |
| add_todo_list, add_task, remove_task, remove_todo_list, mark_completed | edit_todo_list.json | todo_list | `{"action": edit["action"], "title": edit.get("title"), "text": edit.get("text"), "task_id": edit.get("task_id"), "completed": edit.get("completed")}` |

**Note:** `import_workflow` is not a single-edit workflow; it is resolved and applied via `core.graph.batch_edits` (e.g. use the ApplyEdits unit with a list of resolved edits, or run the full assistant workflow).

## How to run (GUI / runner)

1. **Resolve workflow path** from `edit["action"]` (e.g. `"add_unit"` → `gui/flet/components/workflow/edit_workflows/edit_add_unit.json`).
2. **Build initial_inputs:** `{"inject_graph": {"data": graph_dict}}`. Graph must be a dict (use `model_dump(by_alias=True)` if you have a ProcessGraph).
3. **Build unit_param_overrides** for the edit unit (see table above), keyed by the unit **id** (same as type name in these workflows).
4. Call **`run_workflow(path, initial_inputs=..., unit_param_overrides=..., format="dict")`**. Canonical units (including graph_edit) are already registered by `run_workflow`.
5. **Read updated graph:** `outputs[unit_id]["graph"]` (e.g. `outputs["add_unit"]["graph"]`). Convert back to ProcessGraph via `to_process_graph(..., format="dict")` if needed.

## Example (Python)

```python
from pathlib import Path
from runtime.run import run_workflow
from core.normalizer import to_process_graph

EDIT_WORKFLOWS_DIR = Path(__file__).parent  # gui/flet/components/workflow/edit_workflows

def apply_edit_via_workflow(graph_dict: dict, edit: dict) -> dict:
    action = (edit.get("action") or "no_edit").strip()
    if action == "import_workflow":
        # use batch_edits or full assistant workflow
        raise ValueError("import_workflow not supported as single-edit workflow")
    path = EDIT_WORKFLOWS_DIR / f"edit_{action}.json"
    if not path.is_file():
        path = EDIT_WORKFLOWS_DIR / "edit_no_edit.json"
    unit_id = action  # same as type in these workflows
    overrides = {unit_id: _edit_to_params(action, edit)}
    out = run_workflow(path, initial_inputs={"inject_graph": {"data": graph_dict}}, unit_param_overrides=overrides, format="dict")
    return out.get(unit_id, {}).get("graph", graph_dict)
```

Implement `_edit_to_params(action, edit)` per row in the table above.
