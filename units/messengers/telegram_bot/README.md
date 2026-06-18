# README.md

# TelegramBot Unit

Messengers environment unit (`environment_type: messengers`, `add_environment` with `env_id: messengers`).

A unit that integrates a bot-mode Telegram client using python-telegram-bot (v20+, long-polling). It can start/stop the bot, fetch unread messages, send messages, and forward raw Bot API calls to the underlying client. Designed to run async operations on a provided background event loop (executor).

Visit https://core.telegram.org/bots to create a bot and obtain `bot_token`.

Requirements
------------
- python-telegram-bot (v20+): https://github.com/python-telegram-bot/python-telegram-bot
- Python 3.10+ (uses modern typing syntax and asyncio features)

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
- `raw`: any payload dict from supported BotAPI methods

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
- Action selection: inputs are inspected in this priority order: `tg_start`, `tg_stop`, `get_unread`, `send_message`, `raw`. The first non-None input is used.
- `tg_start`: Initializes the Application (if needed) and starts long-polling in a background executor; returns a status update {"type":"status","status":"started"} or already_started.
- `tg_stop`: Decrements refcount and stops the Application when refcount reaches zero; returns {"type":"status","status":"stopped"} or stop_deferred.
- `get_unread`: If needed, starts the app, then returns a snapshot of unread messages tracked in unit state in shape:
```json
{"type":"update", "update": {"chats": [{"chat_id": 123, "unread_count": 2, "chat": {"id": 123},"messages": [...]}], "last_read": {"123": 456}}}
```
By default the unit marks chats as read up to the highest fetched message id (configurable by `mark_read`).
- `send_message`: Requires a dict payload with `chat_id` and `message`. Accepts integer IDs, numeric strings, or username/channel strings (pass-through). Sends via `Application.bot.send_message` and returns message send result (send completion, not delivery/read receipt). If `wait_for_delivery` is true, the unit waits for send to complete and returns `delivered` and `new_message_id`.
- `raw`: If input is ``` json {"method":"<name>", "params": {...}} ``` the unit will attempt to call the `corresponding bot.<name>(**params)` method if safe and available, otherwise attempt bot.request`(...)` as a fallback. Raw calls do not auto-start the app; start the bot via `tg_start first`. Raw calls are restricted from calling private/dunder attributes.

State & Pending Updates
----------------------------------------
- The unit tracks `unread_by_chat` and `last_read_by_chat` in state.
- Incoming updates from handlers are queued to a thread-safe pending_unit_queue and surfaced by `step()` (pending updates take lower priority than direct request results for request-response actions).
- The unit uses an internal `_start_refcount` to support multiple start callers without racing stops.

Params (must be provided in params dict)
----------------------------------------
- `bot_token` (str) - required
- `wait_for_delivery` (bool) — default `true` (send_message)
- `delivery_timeout_s` (int) — default `60` (send_message)
- `mark_read` (bool) — default `true` (get_unread: call readChatInbox after fetch)
- `chat_list_limit` (int) — default `100` (get_unread pagination page size)
- `_needs_executor`: bool — must be `true` to indicate background loop usage

Notes and Design Decisions
--------------------------
- The unit requires a background asyncio event loop (passed via params) to schedule long-polling and other async operations. It validates the loop at step invocation and returns a structured error on missing/invalid loop.
- `send_message` accepts non-numeric chat identifiers and passes them to PTB to allow usernames or channel names (e.g., "@channelname").
- `wait_for_delivery` indicates waiting for the send call to complete; Telegram does not provide guaranteed delivery/read receipts via this call.
- `Raw` method invocation disallows private/dunder method names for safety and attempts to call public bot methods first.
- On operation timeout the unit attempts to cancel the running coroutine to avoid orphaned tasks and returns a structured timeout error to the `error` port.

Examples
--------

Start the bot:
```json
{"tg_start": {"action":"tg_start"}}
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

- Missing/invalid background loop -> returns ``` {"type":"error","error":"Background event loop not provided..."} ``` on the `error` port.
- Timeouts -> returns ``` {"type":"error","error":"operation timed out after <N>s"} ``` and attempts to cancel the underlying coroutine.
- Invalid raw method or params -> returns ``` {"type":"error","error":"invalid method"} ``` or invalid params.

Dependencies
------------

```bash
pip install python-telegram-bot --upgrade
```

# Licensing / Attribution
-----------------------
Depends on python-telegram-bot and Telegram Bot API; ensure compliance with their licenses when packaging or redistributing.
