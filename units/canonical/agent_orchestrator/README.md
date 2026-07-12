# AgentOrchestrator

AI agent turn orchestration unit, which handles all the context and languge support, todo-tasks, tools usage, etc. It might be useful for messengers and AI chat apps integrations. 

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
| `message` | Any | `{"type":"final","message":{...}}` — complete message dict including `graph` (applied graph dict for canvas), `last_apply_result`, `session_language`, `run_output` `llm_system_prompt`, `llm_user_message` |
| `role` | Any | `{"role_id":"...","name":"..."}` — resolved role |
| `error` | Any | `{"type":"error","error":"..."}` or `null` |

## Params

| Param | Type | Description |
|---|---|---|
| `timeout_s` | str | Optional timeout to wait for the final output message (if not provided (None), it waits indefinitely ) |
| `update_pub_endpoint` | str | the unit will publish its updates to this endpoint, if provided (e.g. tcp://127.0.0.1:9903) |
| `run_id` | str | optional run_id which might be used for updates verification on the receiver's end|

timeout_s

## Streaming

LLM token chunks stream through `_stream_callback` in params (same mechanism as all other streaming units). The messenger's existing stream consumer renders them live.


The messenger calls:
```python
run_workflow(
    orchestration_workflow_path,
    initial_inputs={"inject_context": {"data": context_dict}},
    stream_callback=stream_cb,
)
```
