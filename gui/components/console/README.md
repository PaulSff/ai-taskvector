# Workflow Console Technical Summary

The Workflow Console is a remote execution bridge that allows the TaskVector GUI to trigger, monitor, and control workflow runs on a remote runtime via ZeroMQ (ZMQ). It supports both one-shot execution and real-time streaming (keep-alive) modes.


## 1. Architecture Overview

The implementation is split into two primary layers:
- **UI Layer (`console.py`)**: A Flet-based interface providing a collapsible terminal, execution controls (Run/Stop), a real-time timer, and status indicators.
- **Communication Layer (`run_console.py`)**: A ZMQ-based bridge that handles the low-level publishing of jobs and subscription to result streams.


## 2. Communication Protocol

The system uses a slot-based ZMQ architecture to support concurrent executions:
- **Slot Allocation**: A `RoundRobinSlotAllocator` assigns specific ZMQ endpoints to each run to avoid message collisions.
- **Job Publishing**: The `ZmqPublisher` sends the `ProcessGraph` and initial inputs to the runtime.
- **Result Subscription**: The `ZmqSubscriber` listens to four specific topics:
    - `result`: Final output of the workflow.
    - `error`: Runtime exceptions or workflow failures.
    - `token`: Partial text streams (for LLM outputs).
    - `update_batch`: Intermediate state updates for keep-alive workflows.


## 3. Execution Modes

The console supports two distinct operational modes based on the `keep_alive` flag:
- **Normal Mode**: The system waits for the first `result` or `error` message, invokes the result callback, and then closes the connection.
- **Keep-Alive Mode**: The system remains subscribed to the `update_batch` and `token` topics, streaming updates to the UI until an explicit stop action is triggered or a fatal error occurs.


## 4. Key Technical Features

- **Token Buffering**: To prevent UI flickering and broken lines, `console.py` implements a `token_buffer` that only appends text to the terminal once a newline character is detected.
- **Graceful Shutdown**: The `WorkflowRun` class allows the UI to send a `stop_workflow` action via ZMQ and wait for a confirmation (`workflow_status == 'stopped'`) before releasing the communication slot.
- **Timeout Management**: Implements both a global execution timeout (`execution_timeout_s`) and a specific ZMQ subscription timeout to prevent the GUI from hanging on unresponsive runtimes.
