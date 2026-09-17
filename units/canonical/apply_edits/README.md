# ApplyEdits Unit

The ApplyEdits unit is a core process component responsible for applying structural modifications (edits) to a workflow graph. It acts as the execution engine for parsed actions, ensuring that changes to units, connections, and metadata are validated and applied atomically.


## Functionality

The unit takes a current graph state and a set of requested edits, validates them against the `GraphEdit` schema, and applies them sequentially. It supports a wide range of operations including adding/removing units, connecting/disconnecting ports, replacing the entire graph, and managing TODO lists and comments.


## Input Ports

- `graph` (ProcessGraph): The current state of the workflow graph to be modified.
- `actions` (ParsedActions): The set of edits to apply. Can be a `ParsedActions` object, a JSON array of edits, or an object containing an 'edits' key.
- `graph_origin` (str): Optional metadata used to tag the origin of imported workflows.


## Output Ports

- `result` (JsonObject): Detailed execution result, including the final graph and a summary of changes.
- `status` (JsonObject): A status object indicating if the application was attempted, if it succeeded, and any error messages.
- `graph` (ProcessGraph): The resulting graph after edits have been applied.
- `error` (str): A string representation of any error encountered during extraction, validation, or application.


## Key Logic & Safety

1. **Extraction**: Flexible input handling allows the unit to process various action formats.
2. **Validation**: Uses Pydantic (`GraphEdit.model_validate`) to ensure edits are structurally sound before application.
3. **Restriction**: Supports an `allowed_actions` parameter via `params` to restrict the unit to a specific subset of permitted operations, enhancing security and stability.
4. **Normalization**: Converts the input graph to a `ProcessGraph` for internal manipulation and back to a JSON object for output.


## Edit Types Supported

The unit handles various actions including:
- `add_unit`, `remove_unit`, `replace_unit`
- `connect`, `disconnect`
- `set_params`
- `replace_graph`
- `add_comment`, `remove_comment`
- `add_todo_list`, `add_task`, `mark_completed`, etc.
- `import_workflow`
