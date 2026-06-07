# AgentOrchestrator

AI agent turn orchestration unit.

## Input ports

| Port | Type | Description |
|---|---|---|
| `data` | Any | Context dict: `user_message`, `messenger`, `role_id`/`role_hint`, `history`, `session_language`, `last_apply_result`, `graph`, `recent_changes`, `provider`, `cfg`, `rag_index_dir`, `mydata_dir`, `coding_is_allowed`, `contribution_is_allowed` |
| `messenger` | str | Optional messenger id (also accepted in `data.messenger`) |

## Output ports

| Port | Type | Description |
|---|---|---|
| `status` | Any | `{"type":"status","status":"..."}` |
| `token` | Any | `{"type":"token","token":"<full reply>"}` |
| `message` | Any | `{"type":"final","message":{...}}` — complete message dict including `graph` (applied graph dict for canvas), `last_apply_result`, `session_language`, `run_output` |
| `role` | Any | `{"role_id":"...","name":"..."}` — resolved role |
| `error` | Any | `{"type":"error","error":"..."}` or `null` |

## Streaming

LLM token chunks stream through `_stream_callback` in params (same mechanism as all other streaming units). The messenger's existing stream consumer renders them live.

## Usage in orchestration_workflow.json

```json
{
  "units": [
    {"id": "inject_context", "type": "Inject"},
    {"id": "orchestrator", "type": "AgentOrchestrator"}
  ],
  "connections": [
    {"from": "inject_context.data", "to": "orchestrator.data"}
  ]
}
```

The messenger calls:
```python
run_workflow(
    orchestration_workflow_path,
    initial_inputs={"inject_context": {"data": context_dict}},
    stream_callback=stream_cb,
)
```
