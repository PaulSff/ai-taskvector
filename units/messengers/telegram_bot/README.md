# TelegramBot Unit

Messengers environment unit (`environment_type: messengers`, `add_environment` with `env_id: messengers`).

A unit that acts as a ZMQ proxy to an external Telegram Bot Poller service. It publishes commands via ZMQ and subscribes to response and update channels to interact with the Telegram Bot API asynchronously.

Visit https://core.telegram.org/bots to create a bot and obtain `bot_token`.

Ports
-----
Inputs (single dict per port):
- `start`: 
```json 
{"action": "start"} 
```
- `stop`: 
 ```json 
{"action": "stop"} 
```
- `get_unread`: 
```json 
{"action": "get_unread", "messenger": "telegram"} 
```
- `send_message`: 
```json 
{"action": "send_message", "messenger": "telegram", "chat_id": <int_or_str>, "message": "<text>"} 
```
- `raw`: any payload dict from supported BotAPI methods

Outputs:
- `update`: `{"type":"update", "messenger": "telegram", "update": <payload>}`
- `status`: `{"type":"status", "messenger": "telegram", "status": "..."}`
- `error`: `{"type":"error", "messenger": "telegram", "error": "..."}`

Behavior / Actions
------------------
- **Action selection**: Inputs are inspected in this priority order: `start`, `stop`, `get_unread`, `send_message`, `raw`. The first non-None input is used.
- **ZMQ Communication**: The unit does not run the bot itself. It publishes a job to the `zmq_sub_endpoint` and waits for a response on the `response_endpoint` using a unique `run_id`.
- `start`/`stop`: Manages the lifecycle of the local ZMQ listeners and sends stop commands to the remote poller.
- `get_unread`: Requests unread messages from the poller. Supports `mark_read` and `wait_for_delivery` parameters.
- `send_message`: Sends a message via the poller. Supports `wait_for_delivery` to block until the poller confirms the action.
- `raw`: Forwards any dictionary payload directly to the poller as a raw Bot API request.

Params (must be provided in params dict)
----------------------------------------
- `bot_token` (str) - The bot token (usually configured on the poller service, but can be passed via params).
- `wait_for_delivery` (bool) — default `true`
- `delivery_timeout_s` (int) — default `60`
- `mark_read` (bool) — default `true`
- `keep_bot_alive` (bool) — default `false`. If `true`, the unit will not send a stop command to the poller during cleanup, keeping the bot active.
- `zmq_sub_endpoint` (str) - The ZMQ endpoint where the unit publishes jobs to the Telegram bot poller.
- `update_endpoint` (str) - The ZMQ endpoint the unit subscribes to for receiving `update_batch` notifications.
- `response_endpoint` (str) - The ZMQ endpoint the unit subscribes to for receiving `result` and `error` responses.
- `workflow_path` (str) - The workflow path identifier used by the poller to route responses.

Notes and Design Decisions
--------------------------
- **Background Loop**: The unit requires a background asyncio event loop (via `_executor`, `_executor_loop`, or `_background_loop`) to manage ZMQ subscribers.
- **Persistence**: ZMQ listeners for responses and updates remain active until the unit is stopped or cleaned up.
- **Wakeup**: The unit supports `graph_wakeup`. When an `update_batch` is received on the `update_endpoint`, it triggers a `get_unread` wakeup to notify the graph of new messages.

Examples
--------

Start the bot:
```json
{"start": {"action":"start"}}
```

Send a message:
```json
{"send_message": {"action":"send_message", "chat_id": 123456, "message": "Hello"}}
```

Get unread messages:
```json
{"get_unread": {"action":"get_unread", "messenger":"telegram", "account":"<bot>"}}
```

Call a raw Bot API method (requires the bot already started):

```json
{"raw": {"method":"get_me", "params": {}}}
```

Error handling
--------------
- Timeouts -> returns ``` {"type":"error","error":"operation timed out after <N>s"} ``` and attempts to cancel the underlying coroutine.
- Invalid raw method or params -> returns ``` {"type":"error","error":"invalid method"} ``` or invalid params.
