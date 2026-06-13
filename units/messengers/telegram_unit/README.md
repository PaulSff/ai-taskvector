# TelegramClient Unit

Messengers environment unit (`environment_type: messengers`, `add_environment` with `env_id: messengers`).

A unit that interfaces with a local python-telegram (TDLib) client to start/stop the client, fetch unread messages, send messages, and forward raw TDLib-style payloads to the underlying client. Designed to run async operations on a provided background event loop (executor).

Requirements
------------
- python-telegram: https://github.com/alexander-akhmetov/python-telegram
- TDLib: https://github.com/tdlib/td

Ports
-----
Inputs (single dict per port):
- `tg_start`: 
```json 
{"action": "tg_start"} 
```
- `tg_stop`: 
 ```json 
{"action": "tg_stop"} 
```
- `get_unread`: 
```json 
{"action": "get_unread", "messenger": "telegram", "account": "<phone_or_bot>"} 
```
- `send_message`: 
```json 
{"action": "send_message", "messenger": "telegram", "chat_id": <int_or_str>, "message": "<text>"} 
```
- `raw`: any payload dict from supported tdlib API methods (forwarded to `client.call_method` or `handle_update`)

Outputs:
- `update`: 
```json 
{"type":"update","update": <payload>} # result of operations or forwarded payloads
```
- `status`: 
```json 
{"type":"status","status":"<started|stopped|no_result|...>"} # lifecycle/status messages 
```
- `error`: 
```json 
{"type":"error","error":"<message>"} # on failures
```

Behavior / Actions
------------------
- Action selection: The unit examines inputs in this priority order: `tg_start`, `tg_stop`, `get_unread`, `send_message`, `raw`. The first `non-None` input is used.
- `tg_start`: Initializes (if needed) and logs in the `TDLib` client. Returns a status update ```json {"type":"status","status":"started"}```.
- `tg_stop`: Stops the `TDLib` client. Returns ```json {"type":"status","status":"stopped"}```.
- `get_unread`: Logs in if needed, pages `get_chats`, and for each chat with `unread_count > 0` loads history, filters messages newer than `last_read` (tracked in unit state), optionally marks inbox read via `readChatInbox`. Returns ```{"type":"update","update":{"chats":[...],"last_read":{...}}}``` where each chat entry includes `chat_id`, `unread_count`, `chat`, and `messages` (with optional `text` for `messageText`).
- `send_message`: Requires a dict payload with `chat_id` and `message`. Follows the [official python-telegram send_message example](https://github.com/alexander-akhmetov/python-telegram/blob/main/examples/send_message.py): logs in if needed, preloads chats via `get_chats()` (required so TDLib knows the chat), sends the message, waits on the AsyncResult, and optionally waits for `updateMessageSendSucceeded` (unit params `wait_for_delivery`, `delivery_timeout_s`).
- raw payload handling:
  - If payload is a `dict` with ```{"method": "<name>", "params": {...}}```, calls `tg_client.call_method(method, params=...)` and returns its result (prefers `.update attr`).
  - Else if `tg_client.handle_update(payload)` exists, calls it and returns the payload as `update`.
  - Else returns the payload as `update`.

Params (must be provided in params dict)
----------------------------------------
- `api_id` (str or numeric) — required
- `api_hash` (str) — required
- `account` (str) OR bot_token (str) — one required
- `database_encryption_key` (str) — required
- `files_directory` (str) — optional
- `library_path` (str) — optional
- `wait_for_delivery` (bool) — default `true` (send_message)
- `delivery_timeout_s` (int) — default `60` (send_message)
- `mark_read` (bool) — default `true` (get_unread: call readChatInbox after fetch)
- `chat_list_limit` (int) — default `100` (get_unread pagination page size)
- `_needs_executor`: bool — must be `true` to indicate background loop usage


# Installation guide

1. Build the TDLib (or obtain binary):
Insallation command: 
[https://tdlib.github.io/td/build.html?language=Python](https://tdlib.github.io/td/build.html?language=Python)

TDLIb github: 
[https://github.com/tdlib/td](https://github.com/tdlib/td)

2. Set path:
```bash
echo 'export DYLD_LIBRARY_PATH=/full/path/to/td/tdlib/lib:$DYLD_LIBRARY_PATH' >> ~/.zshrc
source ~/.zshrc
```
3. Install python-client package
```bash
git clone https://github.com/alexander-akhmetov/python-telegram.git
cd ai-taskvector
pip install -e ~/python-telegram
```

# Licensing / Attribution
-----------------------
Depends on python-telegram and TDLib licensing; ensure compliance when packaging or redistributing.
