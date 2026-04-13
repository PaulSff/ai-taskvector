# `delegate_request` tool

Hand the chat to another assistant (new session, same user message by default), or drive **auto-delegation** (RAG picks a team member from indexed role docs).

## Parser action

See `prompt.py` for the JSON line (`action`, `delegate_to`, optional `message`). Wired in analyst / workflow designer graphs via the `delegate_request` canonical unit and `process_agent` side channel.

## `tool.yaml`

- No top-level **`workflow`** — delegation is graph-native. **`rag.top_k`** and **`rag.min_score`** resolve as `tool.delegate_request.rag.top_k` / `tool.delegate_request.rag.min_score` for the nested `rag_search` / `rag_filter` inside `auto_delegate_workflow.json` only.

## Auto-delegate graph

`auto_delegate_workflow.json`: user message → `RunWorkflow(rag_context_workflow.json)` → `RagPickDelegatee` → Router → `delegate_request` unit. Started from `gui/chat/auto_delegate_turn.py` when app setting `auto_delegation_is_allowed` is true.
