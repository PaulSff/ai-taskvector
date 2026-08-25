# ZmqOut

`ZmqOut` is a network unit that acts as an asynchronous ZMQ publisher. It validates specific payload types and publishes them to a ZMQ endpoint in a non-blocking, "fire-and-forget" manner using a background event loop.

## Purpose

This unit is designed to send system events, job requests, results, and errors to external services or other workflow instances via ZMQ without stalling the main execution thread of the current workflow.

## Interface

### Input Ports

| Port | Type | Description |
| :--- | :--- | :--- |
| `token` | `Any` | Payload containing `run_id` and `token`. |
| `job` | `Any` | Payload to trigger a new job (requires `run_id` and either `workflow_path` or `workflow_graph`). |
| `result` | `Any` | Payload containing `run_id` and `outputs` dictionary. |
| `update_batch` | `Any` | A dictionary of updates to be published. |
| `error` | `Any` | Payload containing `run_id` and `error` message. |

**Note:** Only one input port should be provided at a time. Providing multiple inputs simultaneously will result in an error.

### Output Ports

| Port | Type | Description |
| :--- | :--- | :--- |
| `bypass` | `Any` | Forwards the validated payload that was successfully queued for publishing. |
| `error` | `str` | Emits error messages if validation fails or if there is a runtime issue (e.g., missing endpoint). |

## Parameters

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `zmq_pub_endpoint` | `str` | **Required** | The ZMQ endpoint URL to publish to. |
| `dedupe` | `bool` | `False` | If `True`, consecutive identical payloads are suppressed. |
| `linger_ms` | `int` | `0` | ZMQ socket linger period in milliseconds. |
| `send_timeout_ms` | `int` | `5000` | ZMQ send timeout in milliseconds. |
| `slow_joiner_seconds` | `float` | `0.5` | Time to wait for slow joiners. |
| `topics` | `ZmqTopics` | `ZmqTopics()` | Custom ZMQ topics for publishing. |

## Technical Behavior

### Asynchronous Publishing
To prevent network latency from blocking the workflow, `ZmqOut` uses `asyncio.run_coroutine_threadsafe` to offload the publishing task to a background event loop provided by the executor. It looks for the loop in the following order of priority:
1. `params['_executor']._loop`
2. `params['_executor_loop']`
3. `params['_background_loop']`

### Validation Logic
Each input port has strict validation requirements:
- **Job:** Must have `run_id` (str) and exactly one of `workflow_path` (str) or `workflow_graph` (dict).
- **Token:** Must have `run_id` (str) and `token` (str).
- **Result:** Must have `run_id` (str) and `outputs` (dict).
- **Error:** Must have `run_id` (str) and `error` (str).

### Resource Management
The unit lazily initializes a `ZmqPublisher` and caches it in the unit state. The publisher is automatically closed when the unit's `cleanup_fn` is called.
