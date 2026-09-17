# ApplyEdits Unit

The ApplyEdits unit is a core process component of the TaskVector framework responsible for applying structural and metadata modifications to a workflow graph based on parsed action requests.


## Overview

ApplyEdits acts as the execution engine for graph modifications. It takes a current graph state and a set of requested edits (ParsedActions), validates them against the system schema, and applies them sequentially to produce a new graph state.


## Input Ports

- `graph` (ProcessGraph): The current state of the workflow graph to be modified.
- `actions` (ParsedActions): The set of edits to apply. This can be a `ParsedActions` object, a JSON array of edits, or an object containing an `edits` key.
- `graph_origin` (str): An optional identifier for the source of the graph, used specifically to patch `import_workflow` actions.


## Output Ports

- `result` (JsonObject): Detailed execution result including the final graph and a list of applied edits.
- `status` (JsonObject): A status object containing `attempted`, `success`, and `error` fields.
- `graph` (ProcessGraph): The resulting graph after edits have been applied (or the original graph if application failed).
- `error` (str): A human-readable error message if the process failed.


## Supported Edit Actions

The unit supports a wide range of graph manipulations, including:
- **Structural**: `add_unit`, `remove_unit`, `connect`, `disconnect`, `replace_unit`, `replace_graph`.
- **Metadata**: `set_params`, `add_comment`, `remove_comment`.
- **Task Management**: `add_todo_list`, `remove_todo_list`, `add_task`, `remove_task`, `mark_completed`, `set_implementer`, `set_deadline`, `set_curator`.
- **Workflow**: `import_workflow`, `add_environment`.


## Error Handling & Validation

The unit implements a strict validation pipeline:
1. **Extraction**: Ensures the input actions are in a compatible format.
2. **Schema Validation**: Uses Pydantic (`GraphEdit.model_validate`) to ensure each edit is well-formed.
3. **Normalization**: Converts the graph to a `ProcessGraph` for internal manipulation.
4. **Application**: Executes edits via `apply_workflow_edits`. If any step fails, it returns a detailed error status without corrupting the original graph.


## Security & Constraints

The unit supports an `allowed_actions` parameter. When provided, the unit will only execute edits that are present in the allowed list, providing a layer of security to prevent unauthorized graph modifications.
