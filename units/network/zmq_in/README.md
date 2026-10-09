# ZmqIn Unit

The `ZmqIn` unit is a generic ZeroMQ SUB transport that allows the TaskVector graph to react to external messages. It subscribes to one or more ZMQ endpoints and triggers a graph wakeup whenever a message is received on a configured topic.

## API Specification

### Input Ports
| Port | Type | Description |
| :--- | :--- | :--- |
| `start` | `dict` | Starts the ZMQ subscribers. Expected: `{"action": "start"}` |
| `stop` | `dict` | Stops and closes the ZMQ subscribers. Expected: `{"action": "stop"}` |

### Output Ports
| Port | Type | Description |
| :--- | :--- | :--- |
| `token` | `dict` | Latest received message for the `token` topic. |
| `job` | `dict` | Latest received message for the `job` topic. |
| `result` | `dict` | Latest received message for the `result` topic. |
| `update_batch` | `dict` | Latest received message for the `update_batch` topic. |
| `error` | `dict` | Error messages. Format: `{"type": "error", "error": "message"}` |

## Configuration

The unit can be configured to subscribe to endpoints in two ways:

1. **Single Endpoint**: Set `params["endpoint"]` to a ZMQ connection string (e.g., `tcp://127.0.0.1:5555`).
2. **JSON Configuration**: Set `params["subscriptions_json_path"]` to a path to a JSON file with the following structure:
   ```json
   {
     "subscriptions": [
       {
         "name": "jobs",
         "sub_endpoint": "tcp://127.0.0.1:5555",
         "topic_idx": "0"
       }
     ],
     "topics": ["job", "result"]
   }
   ```

## Behavior

- **Asynchronous Wakeup**: The unit does not block the graph. It uses a background event loop to listen for messages. When a message arrives, it invokes the `_graph_wakeup_callback`, which tells the executor to rerun the unit.
- **State Management**: Only the *latest* message per topic is retained. If multiple messages arrive before the graph reruns, previous messages are overwritten.
- **Runtime Requirements**: The executor must provide:
    - `_unit_id`: Unique identifier for the unit.
    - `_graph_wakeup_callback`: Callback to trigger graph execution.
    - `_executor` or `_background_loop`: A running `asyncio` event loop.
