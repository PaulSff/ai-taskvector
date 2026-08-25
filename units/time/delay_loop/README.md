# DelayLoop Unit

The `DelayLoop` unit is a timer-based utility that periodically wakes the graph executor and emits a payload. It is ideal for creating polling mechanisms, heartbeat signals, or scheduled triggers within a TaskVector workflow.

## Functionality

The unit runs an asynchronous background loop. When active, it waits for a specified interval, triggers a graph wakeup event, and emits a payload through its output port.

## Ports

### Input Ports
- `control` (Any): Accepts a command dictionary to manage the loop state.
  - `{"action": "start"}`: Starts the periodic emission.
  - `{"action": "stop"}`: Stops the periodic emission.
- `payload` (Any): An optional payload to be emitted. If provided, this takes precedence over the configured parameter.

### Output Ports
- `out` (Any): Emits the configured or input payload on every tick.
- `error` (Any): Emits error details if the unit encounters a runtime issue (e.g., invalid interval configuration).

## Configuration

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `update_interval_s` | float | `1.0` | The interval in seconds between emissions. Must be a positive number. |
| `payload` | Any | `None` | The default payload to emit if the `payload` input port is empty. |

## Technical Details

- **Graph Wakeup**: The unit uses `GraphWakeupEvent` to notify the executor, ensuring that the graph reruns even if no other units are active.
- **Idempotency**: Calling `start` on a loop that is already running has no effect.
- **Async Execution**: The timer runs in a background `asyncio` loop to prevent blocking the main execution thread.
- **State Tracking**: The unit tracks `running` status, `total_ticks`, and `total_errors` in its internal state.

## Example Usage

To start a loop every 5 seconds emitting a "ping" message:
1. Set `update_interval_s` to `5.0` in params.
2. Set `payload` to `"ping"` in params.
3. Send `{"action": "start"}` to the `control` port.