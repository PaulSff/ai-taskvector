# Workflow Console Components

The Console components provide a decoupled execution interface for TaskVector workflows, allowing the GUI to trigger, monitor, and stream results from the runtime engine via an asynchronous messaging layer.


## Overview

The Console is split into two primary layers: the **UI Layer** (`console.py`), which handles the Flet-based visual representation and user interaction, and the **Communication Layer** (`run_console.py`), which manages the ZMQ Pub/Sub lifecycle for job submission and result retrieval.


## Architecture

To prevent the GUI from freezing during long-running workflows, the console uses a decoupled execution model:

1. **Job Submission**: The GUI publishes a workflow job to a ZMQ Publisher endpoint.
2. **Slot Allocation**: A `RoundRobinSlotAllocator` ensures that concurrent runs are distributed across available endpoints to avoid message collisions.
3. **Asynchronous Listening**: A ZMQ Subscriber listens for specific topics (results, tokens, errors, and update batches) on a dedicated response endpoint.
4. **UI Updates**: As messages arrive, they are dispatched to callbacks that update the Flet UI in real-time.


## Execution Modes

The system supports two distinct execution strategies via `run_via_jobs_and_await`:

- **Normal Mode (`keep_alive=False`)**: The system waits for the first final result or a workflow error. Once received, it invokes the result callback and returns the output to the caller. It is subject to a `timeout_s` limit.
- **Keep-Alive Mode (`keep_alive=True`)**: The system remains subscribed indefinitely, invoking the result callback for every update received. This is used for streaming workflows or long-running processes. It does not return until the task is explicitly cancelled or a fatal error occurs.


## Key Components

**`console.py`**:
- `build_workflow_run_console`: The main factory function that creates the collapsible UI.
- `render_token`: Implements a line-buffering mechanism to ensure smooth streaming of LLM tokens.
- `run_async`: Bridges the live canvas graph to the runtime, handling normalization and timer management.

**`run_console.py`**:
- `run_via_jobs_and_await`: The core orchestration function for ZMQ communication.
- `format_run_outputs`: A utility to prettify complex dictionary outputs for console display.
- `ZmqPublisher` / `ZmqSubscriber`: Low-level wrappers for the messaging protocol.


## Messaging Topics

The console listens to the following ZMQ topics:
- `result`: Final workflow outputs.
- `token`: Individual text fragments for streaming displays.
- `error`: Workflow-level exceptions and failures.
- `update_batch`: Intermediate state updates during execution.
