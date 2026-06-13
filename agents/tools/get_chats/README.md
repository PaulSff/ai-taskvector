# `get_chats` tool

Fetch unread chat messages over a supported messenger (Telegram via TDLib) from a structured `get_unread` action in the model output.

## Parser action

See `prompt.py` for payload shape (`action`: `get_unread`, `messenger`, optional `account`).

## `tool.yaml`

- **`workflow`**: `get_chats_workflow.json` — Inject → `TelegramClient` (`get_unread` port) for `get_tool_workflow_path("get_chats")`.
- **`telegram`**: TDLib credentials resolved from `config/app_settings.json` via `settings.telegram_*` keys (same as `send_message`; see `agents/tools/send_message/README.md`).

Unit params on the workflow graph: `mark_read` (default true), `chat_list_limit` (default 100).

## Follow-up

`run_get_chats_follow_up` in `__init__.py` → `TOOL_RUNNERS["get_chats"]` in `registry.py`.
