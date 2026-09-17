# AgentOrchestrator

An AI agent orchestration unit designed to manage the complete lifecycle of an agent's turn. It handles context management, language localization, TODO list tracking, tool execution loops, and integration with external messengers or chat interfaces. 

## Input ports

| Port | Type | Description |
|---|---|---|
| `data` | Any | Context dictionary containing: `user_message`, `messenger`, `role_id`/`role_hint`, `history`, `session_language`, `last_apply_result`, `graph`, `recent_changes`, `state`, `provider`, `cfg`, `rag_index_dir`, `mydata_dir`, `coding_is_allowed`, `contribution_is_allowed`, `training_config_path`, `current_date` |
| `messenger` | str | Optional messenger id (also accepted in `data.messenger`) |

## Output ports

| Port | Type | Description |
|---|---|---|
| `status` | Any | `{"type":"status","status":"..."}` |
| `token` | Any | `{"type":"token","token":"<full reply>"}` |
| `message` | Any | `{"type":"final","message":{...}}` — complete message dict including `graph` (applied graph dict for canvas), `last_apply_result`, `session_language`, `run_output`, `llm_system_prompt`, `llm_user_message` |
| `role` | Any | `{"role_id":"...","name":"..."}` — resolved role |
| `error` | Any | `{"type":"error","error":"..."}` or `null` |

## Params

| Param | Type | Description |
|---|---|---|
| `timeout_s` | float/int | Optional timeout to wait for the final output message (if not provided, it waits indefinitely) |
| `update_pub_endpoint` | str | the unit will publish its updates to this endpoint, if provided (e.g. tcp://127.0.0.1:9903) |
| `run_id` | str | optional run_id which might be used for updates verification on the receiver's end|

## Streaming & Execution

The unit operates an internal loop: it calls the LLM, processes tool requests, and repeats until a final answer is reached or a timeout occurs. 

LLM token chunks are streamed via the `_stream_callback` provided in the params, allowing the UI/messenger to render responses in real-time as they are generated.


The messenger calls:
```python
run_workflow(
    orchestration_workflow_path,
    initial_inputs={"inject_context": {"data": context_dict}},
    stream_callback=stream_cb,
)
```
