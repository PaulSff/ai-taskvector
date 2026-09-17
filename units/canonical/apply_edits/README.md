# ApplyEdits Unit

The ApplyEdits unit is a core process component responsible for applying a sequence of parsed graph modifications (edits) to a workflow graph. It ensures that changes are validated, normalized, and safely applied to the graph state.


## Overview

ApplyEdits acts as the bridge between a high-level intent (parsed actions) and the actual structural modification of the TaskVector graph. It handles the extraction of edits from various input formats, validates them against the `GraphEdit` schema, and executes them using the `apply_workflow_edits` engine.


## Input Ports

- `graph` (ProcessGraph): The current state of the workflow graph to be modified.
- `actions` (ParsedActions): The set of edits to apply. Can be a `ParsedActions` object, a JSON array of edits, or an object containing an `edits` key.
- `graph_origin` (str): Optional metadata used to tag the origin of imported workflows.


## Output Ports

- `result` (JsonObject): A detailed result object containing the application kind (`no_edits`, `applied`, `apply_failed`), the resulting graph, and the list of edits processed.
- `status` (JsonObject): A status object indicating if the operation was `attempted`, if it was a `success`, and any associated `error` or `edits_summary`.
- `graph` (ProcessGraph): The updated graph after edits have been applied (or the original graph if application failed).
- `error` (str): A human-readable error message if the process failed.


## Key Logic & Features

1. **Flexible Extraction**: The `_extract_edits` helper allows the unit to accept edits in multiple formats, making it compatible with various agent output styles.
2. **Strict Validation**: Every edit is validated using Pydantic's `GraphEdit.model_validate` to prevent corrupted graph states.
3. **Action Filtering**: Through the `allowed_actions` parameter, the unit can be restricted to only allow specific types of modifications (e.g., only allowing `add_comment` but not `remove_unit`).
4. **Human-Readable Summaries**: The `_edits_summary` function converts technical JSON edits into a concise string (e.g., `add_unit unit_1 (Process)`) for logging and debugging purposes.
5. **Atomic-like Application**: Edits are applied sequentially via `MultipleEditsSequential`, ensuring a predictable order of operations.


## Payload Examples

### Input: `actions` port

**Option 1: Simple Array of Edits**
```json
[
  {
    "action": "add_unit",
    "unit": { "id": "logger_1", "type": "LoggerUnit" }
  },
  {
    "action": "connect",
    "from": "source_unit",
    "to": "logger_1"
  }
]
```

**Option 2: ParsedActions Object**
```json
{
  "edits": [
    {
      "action": "add_comment",
      "info": "Adding a new processing node"
    }
  ],
  "tool_actions": {}
}
```

### Output: `status` port

**Successful Application**
```json
{
  "attempted": true,
  "success": true,
  "error": null,
  "edits_summary": "add_unit logger_1 (LoggerUnit); connect source_unit->logger_1"
}
```

## Error Handling States

- **Malformed Input**: Returns `attempted=False` if the `actions` input cannot be parsed.
- **Validation Failure**: Returns `attempted=False` if the edits do not match the `GraphEdit` schema.
- **Application Failure**: Returns `attempted=True, success=False` if the edits were valid but could not be applied to the specific graph structure (e.g., trying to connect a non-existent unit).
