# CheckTodo Unit

The `CheckTodo` unit is a utility component within the TaskVector framework designed to scan a workflow graph for incomplete tasks. It ensures that the agentic loop can identify pending work across different graph sources.

## Overview

This unit checks for tasks where `completed` is set to `False`. It is particularly useful for implementing "todo-driven" agentic loops where the agent must verify if there are remaining tasks before concluding a process.

## Graph Resolution Order

To ensure flexibility, the unit attempts to locate a workflow graph in the following priority order:

1. **Input Port**: If a graph is provided directly via the `graph` input port, it is used immediately.
2. **Live Graph**: If no input is provided, it attempts to retrieve the current active graph using `get_live_graph_dict()`.
3. **Latest Saved Graph**: As a fallback, it imports the most recently saved workflow graph using `import_latest_workflow_graph()`.

## Interface

### Input Ports
| Port | Type | Description |
| :--- | :--- | :--- |
| `check_todo` | `Any` | Required. Must be a dictionary: `{"action": "check_todo"}`. |
| `graph` | `Any` | Optional. A dictionary representing the `ProcessGraph` to be analyzed. |

### Output Ports
| Port | Type | Description |
| :--- | :--- | :--- |
| `tasks_todo` | `Any` | Returns an update object containing a list of incomplete tasks, or `None` on error. |
| `error` | `Any` | Returns an error object if the operation fails, or `None` on success. |

## Data Formats

### Successful Response
When incomplete tasks are found, the `tasks_todo` port outputs:

```json
{
    "type": "update",
    "update": {
        "tasks_todo": [
            {
                "todo_list_id": "todo-1",
                "task": {
                    "id": "task-1",
                    "completed": false
                }
            }
        ]
    }
}
```

### Error Response
If the graph is missing or invalid, the `error` port outputs:

```json
{
    "error": "invalid_graph",
    "message": "Detailed Pydantic validation error message..."
}
```

## Implementation Details
- **Validation**: Uses `core.schemas.ProcessGraph` (Pydantic) to validate the graph structure.
- **Serialization**: Includes a `_to_jsonable` helper to ensure Pydantic models are converted to standard JSON types before output.
- **Complexity**: Time complexity is $O(T)$ where $T$ is the total number of tasks across all todo lists in the graph.