# `send_message` tool

Send a chat message over a supported messenger (Telegram via TDLib) from a structured `send_message` action in the model output.

## Parser action

See `prompt.py` for payload shape (`action`, `messenger`, `chat_id`, `message`).

## `tool.yaml`

- **`workflow`**: `send_message_workflow.json` — Inject → `TelegramClient` (`send_message` port) for `get_tool_workflow_path("send_message")`.
- **`telegram`**: TDLib credentials resolved from `config/app_settings.json` via `settings.telegram_*` keys (see below).

## Telegram setup

Add these keys to `config/app_settings.json` (or override via deployment settings):

| Key | Description |
|-----|-------------|
| `telegram_api_id` | App id from [my.telegram.org](https://my.telegram.org/apps/) |
| `telegram_api_hash` | App api_hash |
| `telegram_account` | Phone number (user account) **or** leave empty when using a bot |
| `telegram_bot_token` | Bot token **or** leave empty when using a user account |
| `telegram_database_encryption_key` | TDLib database encryption key (any secret string) |
| `telegram_files_directory` | Optional: TDLib files directory |
| `telegram_library_path` | Optional: path to TDLib shared library |

Requires [python-telegram](https://github.com/alexander-akhmetov/python-telegram) and a built TDLib — see `units/messengers/telegram_client/README.md`.

## Follow-up

`run_send_message_follow_up` in `__init__.py` → `TOOL_RUNNERS["send_message"]` in `registry.py`.
