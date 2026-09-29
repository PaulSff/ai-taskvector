# AgentOrchestrator

An AI agent orchestration unit that manages the execution of an agent's turn. It acts as a bridge between the synchronous unit runtime and the asynchronous agent handlers, managing session state, role resolution, and the orchestration of the agent's response pipeline. 

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
| `message` | Any | Either `{"type":"final","message":{...}}` (complete response) or `{"type":"delegate","delegate_to":"..."}` (request to hand over to another agent role) |
| `role` | Any | `{"role_id":"...","name":"..."}` — resolved role |
| `error` | Any | `{"type":"error","error":"..."}` or `null` |

## Params

| Param | Type | Description |
|---|---|---|
| `timeout_s` | float/int | Optional timeout to wait for the final output message (if not provided, it waits indefinitely) |
| `update_pub_endpoint` | str | the unit will publish its updates to this endpoint, if provided (e.g. tcp://127.0.0.1:9903) |
| `run_id` | str | optional run_id which might be used for updates verification on the receiver's end|

## Streaming & Execution

The unit resolves the appropriate `RoleChatHandler` for the given `role_id` and executes the turn asynchronously. It provides the agent with a `TurnRuntimeProxy` allowing it to interact with the workflow graph, append messages to history, and run nested workflows. 

LLM token chunks are streamed via the `_stream_callback` provided in the params, allowing the UI/messenger to render responses in real-time as they are generated.


The messenger calls:
```python
run_workflow(
    orchestration_workflow_path,
    initial_inputs={"inject_context": {"data": context_dict}},
    stream_callback=stream_cb,
)
```
