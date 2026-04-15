# `delegate_request` tool

Hand the chat to another assistant (new session, same user message by default), or drive **auto-delegation** (RAG picks a team member from indexed role docs).

## Parser action

See `prompt.py` for the JSON line (`action`, `delegate_to`, optional `message`). Wired in analyst / workflow designer graphs via the `delegate_request` canonical unit and `process_agent` side channel.

## `tool.yaml`

- No top-level **`workflow`** — delegation is graph-native. For the nested `rag_context_workflow` inside `auto_delegate_workflow.json` only: **`rag.top_k`** → `rag_search`, **`rag.min_score`** → `rag_filter` (score threshold), **`rag.metadata_file_path_contains`** → `rag_search` so retrieval keeps chunks whose indexed `file_path` contains that substring (default: `assistants_team_members.md`, the materialized team-member / `responsibility_description` doc under `mydata/TaskVector/`). The data_bi **`Filter`** unit cannot match nested `metadata`; path restriction is implemented inside **`RagSearch`** / `RAGIndex.search`.

## Auto-delegate graph

`auto_delegate_workflow.json`: user message → `RunWorkflow(rag_context_workflow.json)` → `RagPickDelegatee` → Router → `delegate_request` unit. Started from `gui/chat/auto_delegate_turn.py` when app setting `auto_delegation_is_allowed` is true.
