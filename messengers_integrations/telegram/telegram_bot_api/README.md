# TelegramBotPoller

## Overview
`TelegramBotPoller` is a component that:
- Starts a python-telegram-bot (PTB) polling loop.
- Streams incoming Telegram messages/events to an async subscriber via `subscribe()`.
- Provides preserved operations to:
  - Fetch unread messages using *local JSON persistence* (`get_unread`)
  - Send messages (`send_message`)
  - Call allowed PTB/bot methods generically (`raw`)

## Key Concepts
- **Streaming:** Use `subscribe()` to receive events of type `update_batch`.
- **Persistence:** Messages and “last read” pointers are stored in a JSON file on disk.
- **Locking:** Internal state mutations are guarded by a `threading.RLock`.

## Public API

### Lifecycle
- `await poller.start() -> dict`
  - Starts polling if not already started.
  - If already running, returns `{"type":"status","status":"already_started"}`.
- `await poller.stop(force: bool = False) -> dict`
  - Stops polling (and ends the subscriber stream when fully closed).

### Streaming
- `poller.subscribe() -> AsyncIterator[dict]`
  - Only one subscriber is supported; a second call raises `RuntimeError`.
  - Yields dicts like:
    - `{"type":"update_batch","update":..., "status":..., "error":...}`

### Operations
- `await poller.get_unread() -> dict`
  - Returns local unread chats based on:
    - `messages_by_chat_id`
    - `last_read_by_chat_id`
  - Params:
    - `mark_read` (bool, default `True`)
  - If `mark_read=True`, updates `last_read_by_chat_id` and persists to disk.

- `await poller.send_message(chat_id, message, wait_for_delivery=None) -> dict`
  - Sends a text message.
  - Params:
    - `chat_id`: int or numeric string
    - `message`: any value (converted to `str`)
    - `wait_for_delivery`: optional bool; defaults to `params["wait_for_delivery"]` or `True`

- `await poller.raw(method, params=None) -> dict`
  - Calls a method on PTB bot / bot.request if available.
  - Blocks methods starting with `_` or `__`.
  - Params:
    - `method`: str
    - `params`: dict

## Configuration Parameters (`params` passed to constructor)
At minimum:
- `bot_token` or `account` (string): required

Optional:
- `connect_timeout` (float): default 10
- `read_timeout` (float): default 20
- `pool_timeout` (float): default 5
- `wait_for_delivery` (bool): default `True`
- `mark_read` (bool): used by `get_unread` default `True`

## Persistence
- Stores state in a JSON file under:
  - `/mydata/tg_messages/`
- Filename includes a timestamp suffix:
  - `tg_messages<timestamp>.json`
- Persisted fields:
  - `messages_by_chat_id`
  - `last_read_by_chat_id`
  - `created_utc`, `updated_utc`
- Blacklist:
```json
{
  "123456789:ABCDEF_your_bot_token": ["111222333", "444555666"],
  "987654321:ZZTOP_another_bot_token": ["777888999"]
}
```
If Forbidden is received, meaning a chat_id is blocked by its owner, the chat_id gets blocklisted. Accounts (chat_ids) are removed from blacklist on any message coming form these accounts. The blocklisted chat_ids are refused to send messages to. 

## Usage Example

### 1) Streaming example

```python
import asyncio

async def main():
    poller = TelegramBotPoller({
        "bot_token": "YOUR_TOKEN",
        # optional:
        # "mark_read": True,
        # "wait_for_delivery": True,
    })

    await poller.start()

    async for ev in poller.subscribe():
        # ev example:
        # {"type":"update_batch","update": {"chat_id": ..., "message": ...}, ...}
        print(ev)

asyncio.run(main())
```

### Get unread + mark read
```python
async def unread_demo(poller: TelegramBotPoller):
    res = await poller.get_unread()
    print(res["update"]["chats"])

```

### Send message

```python
async def send_demo(poller: TelegramBotPoller):
    await poller.send_message(chat_id=123456789, message="Hello!")
```


### Raw method call

```python
async def raw_demo(poller: TelegramBotPoller):
    res = await poller.raw("send_message", {"chat_id": 123, "text": "Hi"})
    print(res)
```


## Notes / Behavior Details

- `send_message()` and `raw()` require that the PTB app is initialized:
   - You must call await `poller.start()` first.
- `get_unread()` computes unread strictly from persisted state:
   - It does not query Telegram for unread counters.
Only one subscriber is allowed via subscribe().

## Stopping

- Call `await poller.stop(force=False`) when finished.
- Stopping ends the event stream once the component fully closes.

# Dependencies


```bash
pip install python-telegram-bot --upgrade
```

# Licensing / Attribution
-----------------------
Depends on python-telegram-bot and Telegram Bot API; ensure compliance with their licenses when packaging or redistributing.
