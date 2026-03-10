# Graph Edit Units

Env-agnostic units used in assistant edit workflows. Each unit applies one edit action: it receives the current graph on input and outputs the updated graph. Validation and apply logic live in `assistants/graph_edits.apply_graph_edit`.

## Structure

Each unit lives in its own folder with a README and implementation (see [canonical/split](../../canonical/split/README.md) for the pattern):

| Unit | Purpose |
|------|---------|
| **inject** | Output the graph from executor `initial_inputs` (no upstream connection). |
| **add_unit** | Add one unit to the graph. Params: `unit` (id, type, params). |
| **add_pipeline** | Add pipeline (RLGym, RLOracle, etc.). Params: `pipeline`. |
| **remove_unit** | Remove unit by `unit_id`. |
| **connect** | Connect two units. Params: `from_id`, `to_id`, optional ports. |
| **disconnect** | Disconnect two units. Params: `from_id`, `to_id`. |
| **replace_unit** | Replace unit. Params: `find_unit`, `replace_with`. |
| **replace_graph** | Replace full graph. Params: `units`, `connections`. |
| **add_code_block** | Add code block. Params: `code_block`. |
| **add_comment** | Add comment (metadata). Params: `info`, `commenter?`. |
| **add_environment** | Add environment tag. Params: `env_id`. |
| **no_edit** | Pass-through; graph unchanged. Params: `reason?`. |
| **add_todo_list** | Add todo list. Params: `title?`. |
| **remove_todo_list** | Remove todo list. |
| **add_task** | Add task. Params: `text`. |
| **remove_task** | Remove task. Params: `task_id`. |
| **mark_completed** | Mark task completed. Params: `task_id`, `completed?`. |

Shared helper: `_apply.apply_edit(inputs, state, edit)` calls `apply_graph_edit` and returns `(outputs, state)`.
