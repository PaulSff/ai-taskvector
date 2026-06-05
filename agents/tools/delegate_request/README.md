# `delegate_request` tool

Hand the current chat session to another agent role.

## Parser action

See `prompt.py` for the JSON line (`action`, `delegate_to`, optional `message`). Wired into analyst / workflow-designer / dispatcher graphs via the `delegate_request` canonical unit and the `ProcessAgent` side channel. The parser should emit the following JSON object:

```json
{ "action": "delegate_request", "delegate_to": "workflow_designer", "message": "..." }
```

## Auto-delegation (dispatcher role)

Automatic role selection before a chat turn is handled by the **dispatcher** role (`agents/roles/dispatcher/`), not by this tool directly. When `auto_delegation_is_allowed` is enabled in settings, chat runs `dispatcher_workflow.json`, which uses an LLM to pick the best role and then calls this tool's unit to perform the handoff.
