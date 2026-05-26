# `delegate_request` tool

Hand the chat to another assistant, or drive **auto-delegation** workflow using LLM-based analysis on the user_message to pick the best suitable role to handle.

## Parser action

See `prompt.py` for the JSON line (`action`, `delegate_to`, optional `message`). Wired into analyst / workflow-designer graphs via the `delegate_request` canonical unit and the `ProcessAgent` side channel. The parser should emit the following JSON object:

```json
{ "action": "delegate\_request", "delegate\_to": "workflow\_designer", "message": "..." }
