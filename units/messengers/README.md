# Messengers environment

Python-only units for chat/messenger integrations (Telegram via TDLib today).

## Units

| Unit | Description |
|------|-------------|
| **TelegramClient** | Start/stop TDLib client, fetch chats, send messages, raw TDLib calls |

See `telegram_unit/README.md` for Telegram setup (python-telegram, TDLib, credentials).

## Using in workflows

1. Use **`add_environment`** with `env_id: messengers` so **TelegramClient** appears in the Units Library.
2. Set **`environment_type`** to **`messengers`** when the workflow is messenger-focused.

Follow-up tools `get_chats` and `send_message` register messengers units automatically when run.
