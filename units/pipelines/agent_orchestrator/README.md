# ChatOrchestrator

Messenger-agnostic chat orchestration pipeline. Wraps the full dispatcher → role-resolver → agent-turn chain as a reusable pipeline type.

## Topology (`workflow.json`)

```
inject_context
    │
    ├─► build_dispatch_payload (PayloadTransform)
    │       builds {run_workflow: {path, initial_inputs}} when auto_delegation_is_allowed=true
    │       else emits {} → RunWorkflow silently no-ops
    │
    ├─► run_dispatcher (RunWorkflow)
    │       runs agents/roles/dispatcher/dispatcher_workflow.json
    │       outputs dispatcher_workflow outputs (delegate_req.data)
    │
    ├─► merge_dispatch (Aggregate)   keys: [dispatcher_out, context]
    │
    ├─► resolve_role (PayloadTransform)
    │       delegate route:  full context dict with role_id replaced by dispatcher suggestion
    │       default route:   full context dict unchanged  {"_raw": "context"}
    │
    └─► orchestrator (AgentOrchestrator)
            full agent turn: role workflow + follow-up chain + apply/validate + post-apply
```

## Input ports (when used as `data` on the outer inject)

| Field | Type | Description |
|---|---|---|
| `user_message` | str | Normalised user text (with graph refs merged in) |
| `messenger` | str | Source messenger id, e.g. `"taskvector"` |
| `role_id` | str | Role hint from the UI dropdown |
| `history` | list | Conversation history |
| `session_language` | str | Pinned session language |
| `last_apply_result` | dict\|null | Last apply result for LLM self-correction context |
| `graph` | dict\|null | Current workflow graph |
| `recent_changes` | str\|null | Recent graph diff |
| `auto_delegation_is_allowed` | bool | Whether to run the dispatcher |
| `auto_delegate_workflow_path` | str | Absolute path to dispatcher_workflow.json |
| `provider`, `cfg` | str, dict | LLM provider config |
| `rag_index_dir`, `mydata_dir` | str | Data directories |
| `coding_is_allowed`, `contribution_is_allowed` | bool | Feature flags |

## Output ports

| Port | Type | Description |
|---|---|---|
| `status` | Any | `{"type":"status","status":"..."}` |
| `token` | Any | `{"type":"token","token":"<full reply>"}` |
| `message` | Any | `{"type":"final","message":{...}}` — includes `graph`, `last_apply_result`, `session_language` |
| `role` | Any | `{"role_id":"...","name":"..."}` |
| `error` | Any | `{"type":"error","error":"..."}` or `null` |

## Delegation logic

`build_dispatch_payload` + `run_dispatcher` handle the optional pre-turn dispatcher call. `resolve_role` resolves the final `role_id`:

- Dispatcher disabled → `{"_raw": "context"}` pass-through (original `role_id`)
- Dispatcher returned `"None"` or failed → same pass-through
- Dispatcher returned a real role → full context rebuilt with `role_id` overridden
