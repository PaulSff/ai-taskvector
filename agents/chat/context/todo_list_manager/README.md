# TodoListManager

`TodoListManager` is a specialized utility module within the TaskVector framework designed to automate the lifecycle of To-Do lists embedded in a `ProcessGraph`. Rather than manually tracking configuration gaps, this manager automatically injects tasks into the graph based on structural changes and external communication events.

## Core Philosophy

Unlike standard state modifiers, the `TodoListManager` treats To-Do list updates as **workflows**. It uses a dedicated `todo_list` workflow to apply changes, ensuring that all modifications to the graph's metadata are consistent, traceable, and follow the framework's execution patterns.

## Key Features

### 1. Automated Workflow Sanity Checks
The manager monitors graph edits and automatically queues tasks to prevent common configuration errors:

| Trigger | Generated Task |
| :--- | :--- |
| **Adding Units** | Ensure units are connected $\rightarrow$ Check unit parameters |
| **Adding Code Units** | Review/Add code block for `Function` or `Script` units |
| **Running Workflow** | Enable debug mode $\rightarrow$ Prepare initial input data |
| **Importing Workflow** | Review the imported workflow structure |

### 2. Telegram Communication Tracking
The manager integrates with Telegram history to ensure no user message goes unanswered:
- **Pending Task Creation**: Detects unhandled messages and creates a "Reply-to" task in the `TG_TODO_LIST`.
- **Automatic Resolution**: Removes the corresponding task once a response is detected in the history.
- **Blacklist Support**: Automatically clears tasks for blacklisted chat IDs.
- **Deadline Management**: Supports setting deadlines for communication tasks to ensure timely responses.

### 3. Intelligent Deduplication
To avoid cluttering the graph, the manager performs checks before adding any task:
- It verifies if an open task with the same text already exists.
- It uses unique keys (via `reply_key_from_task_text`) to track specific Telegram messages across sessions.

## 🏗 Technical Architecture

### Data Flow
1. **Event Trigger**: An action occurs (e.g., `import_workflow` or a new TG message).
2. **Edit Queueing**: The manager gathers required changes into a `TodoEdit` list.
3. **Sequential Execution**: Multiple edits are wrapped in `as_todo_params_sequential`.
4. **Workflow Run**: The `_run_todo_list_workflow` function executes the internal `todo_list` workflow, which returns the updated `ProcessGraph`.

### Key Functions
- `augment_graph_with_client_tasks()`: The primary entry point for the Workflow Designer to add follow-up tasks after a round of edits.
- `add_tasks_for_unhandled_tg_messages()`: The synchronization loop for Telegram-based task management.
- `_ensure_todo_list_exists()`: Guarantees that the required list (Graph or TG) is present before adding tasks.

## Configuration

The component relies on constants defined in `gui.components.settings`:
- `GRAPH_TODO_LIST_ID`: The ID for the main workflow configuration list.
- `TG_TODO_LIST_ID`: The ID for the Telegram communication list.
- `MESSAGES_DIR`: The directory where Telegram conversation history is stored.
