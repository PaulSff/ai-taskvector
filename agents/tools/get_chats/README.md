# `get_chats` tool

Fetch current chat updates over a supported messenger (Telegram via TDLib) from a structured `get_chats` action in the model output.

## Parser action

See `prompt.py` for payload shape (`action`, `messenger`, optional `account`).

## `tool.yaml`

- **`workflow`**: `get_chats_workflow.json` — Inject → `TelegramClient` (`get_chats` port) for `get_tool_workflow_path("get_chats")`.
- **`telegram`**: TDLib credentials resolved from `config/app_settings.json` via `settings.telegram_*` keys (same as `send_message`; see `agents/tools/send_message/README.md`).

## Follow-up

`run_get_chats_follow_up` in `__init__.py` → `TOOL_RUNNERS["get_chats"]` in `registry.py`.
