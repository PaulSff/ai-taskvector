# Agentic Loop Service

The Agentic Loop is a subscriber-driven orchestration system that monitors for unread messenger chats and incomplete todo tasks, triggering autonomous agent turns to process and resolve them.


## Architecture Overview

The service operates as a background poller that bridges external event triggers (via ZMQ/Subscribers) to the agentic execution engine. It ensures that work is processed concurrently across different sessions but serialized within a single session to prevent race conditions.


## Core Components

### 1. `loop_poller.py` (The Orchestrator)
- **Lifecycle Management**: Handles startup, shutdown, and process locking using `fcntl` to prevent multiple instances.
- **Coordination**: Manages the `FollowupCtxSubscriber` (event source) and `AgenticTurnQueue` (execution manager).
- **Validation**: Ensures incoming events are normalized into valid jobs containing exactly one trigger (either unread chats or incomplete tasks).

### 2. `follow_up_ctx_subscriber.py` (The Event Listener)
- **ZMQ Integration**: Subscribes to `update_batch` topic across multiple endpoints (Unread Messages and Todo updates).
- **Input API**: Accepts a JSON dictionary payload. The expected format is a batch update containing triggers:
  - `unread_chats`: List of chat IDs with pending messages.
  - `incomplete_tasks`: List of todo list IDs with pending tasks.
  - *Example*: `{"unread_chats": ["chat_123"], "incomplete_tasks": []}`

### 3. `update_to_agentic_jobs.py` (The Normalizer)
- **Data Translation**: Converts raw subscriber payloads into `AgenticJob` objects.
- **Session Mapping**: 
  - For chats: `chat_id` $\rightarrow$ `session_id`.
  - For todo lists: `todo_list_id` $\rightarrow$ `session_id`.
- **Filtering**: Filters out completed tasks or chats with no unread messages.


## Execution Flow

### 4. `run_agentic_loop.py` (The Executor)
When a job is dequeued, the following sequence occurs:
1. **Graph Loading**: Attempts to fetch the live canvas graph; falls back to the latest imported workflow graph.
2. **Task Generation**: If triggered by unread chats, it automatically creates new todo tasks for unhandled messages.
3. **Persistence**: Saves the updated workflow graph to disk before execution.
4. **Turn Execution**: Formats a user message using predefined templates and calls `handle_turn` to process the agentic logic.
5. **Post-Processing**: Executes the `handle_tasks_expired_hook` to clean up or alert on overdue tasks.


## Data Flow Summary

`External Event` $\rightarrow$ `FollowupCtxSubscriber` $\rightarrow$ `update_to_agentic_jobs` $\rightarrow$ `AgenticTurnQueue` $\rightarrow$ `run_agentic_loop` $\rightarrow$ `handle_turn` $\rightarrow$ `Workflow Graph Update`


## Configuration & Constraints

- **Concurrency**: Controlled by `MAX_CONCURRENCY` and `QUEUE_SIZE` defined in `cfg_helpers`.
- **Strictness**: A job must contain *exactly one* of `unread_chats` or `incomplete_tasks`. If both or neither are present, the job is rejected.
