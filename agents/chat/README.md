# Turn Driver

The `turn_driver` module is the main API entry point for messengers to connect to the AI orchestration pipeline. It manages multi-session, thread-safe interactions, streaming responses, and workflow state synchronization.

## Overview

Unlike a simple request-response loop, `turn_driver.py` coordinates with a ZMQ-based job system to run orchestration workflows. It handles the lifecycle of a "turn," including session recovery, token streaming to the UI, and applying graph edits to the canvas in real-time.

## Key Responsibilities

- **Session Management**: Creates, restores, and persists chat sessions (keyed by `session_id`).
- **Workflow Orchestration**: Dispatches jobs to the orchestration pipeline via `publish_job_and_wait`.
- **Real-time Streaming**: Streams LLM tokens and status updates (e.g., "working", "applying") to the UI via callbacks.
- **Graph Synchronization**: Detects and applies workflow graph changes mid-turn to update the user's canvas.
- **Auto-Naming**: Automatically suggests and renames chat history files based on the first user message.

## Core API

### `handle_turn(...)`

The primary asynchronous entry point for processing a user message.

**Key Arguments:**
- `session_id` (str | None): ID of the session. Creates a new one if None.
- `user_message` (str): The raw input from the user.
- `messenger` (str): Identifier for the transport layer.
- `planning_mode` (bool): If True, prepends a planning prefix to trigger the Planner agent.
- `graph_dict` (ProcessGraph | None): The current workflow graph to be used as context.
- `role_id` (str): The agent role to invoke (defaults to `ANALYST_ROLE_ID`).
- `stream_callback` (Callable): Async callback for streaming tokens to the UI.
- `on_apply` (Callable): Async callback triggered when the agent modifies the workflow graph.
- `on_turn_status` (Callable): Async callback to update the UI on the turn's current state (running $\rightarrow$ working $\rightarrow$ applying $\rightarrow$ done).

**Returns:**
- `Data | None`: The final output from the orchestrator.

### Session Management APIs
- `create_session(session_id)`: Initializes a session.
- `restore_session(session_id, path, payload)`: Loads a session from a disk snapshot.
- `persist_session(session_id, agent_selected)`: Saves the current session state to disk.
- `append_session_message(session_id, msg)`: Manually injects a message into the history.

## Logic Flow

1. **Session Setup**: Retrieves or creates the session and ensures a chat history path exists.
2. **Context Assembly**: Builds a comprehensive context object including history, RAG settings, and LLM provider configs.
3. **Job Dispatch**: Publishes a job to the orchestration pipeline and waits for the result.
4. **Streaming Loop**: 
    - `_token_cb`: Handles raw token streams and updates the session buffer.
    - `_in_progress_batch_cb`: Handles mid-run updates, including graph edits and status changes.
5. **Finalization**: Extracts the final message, updates session language/state, and marks the turn as complete.

## Usage Example

```python
import asyncio
from agents.chat.turn_driver import handle_turn

async def main():
    async def my_stream_cb(sid, token):
        print(f"Streaming: {token}", end="")

    result = await handle_turn(
        session_id="session_123",
        user_message="Design a new data pipeline",
        messenger="web_ui",
        stream_callback=my_stream_cb
    )
    print("\nTurn complete.")

asyncio.run(main())
```

## Dependencies
- `agents.chat.session`: For thread-safe session state.
- `services.zmq.zmq_messaging`: For asynchronous job dispatch.
- `core.schemas.graph_edit_api`: For validating workflow edits.
