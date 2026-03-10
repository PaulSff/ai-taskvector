# Assistant workflow (full pipeline)

End-to-end flow from observation sources to graph edits. **Chat is not a unit in the flow** — it is the **caller**: it runs the flow (e.g. `run_assistant_workflow`), supplies all sources via `initial_inputs` to **Inject** units, and consumes the flow’s outputs (response, result, status).

```
  CALLER (e.g. Chat): runs the flow, supplies initial_inputs per Inject, consumes response + result + status
                                        │
          initial_inputs[id] = {"data": value}  for each Inject
                                        │
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  INJECT UNITS (one per source)                                                            │
│  units/env_agnostic/inject  type: Inject                                                  │
│  inject_user_message │ inject_graph_summary │ inject_units_library │ inject_rag_context   │
│  inject_turn_state │ inject_recent_changes_block │ inject_last_edit_block                  │
│  inject_graph (→ Process only)                                                            │
└─────────────────────────────────────────────────────────────────────────────────────────┘
     │ data (each)                    │ data (inject_graph)
     ▼                                │
┌────────────────────────────┐        │
│  MERGE (merge_llm)         │        │
│  units/canonical/merge     │        │  in_0..in_6 → single `data` dict
│  N inputs → single `data`  │        │
└────────────────────────────┘        │
     │ data                            │
     ▼                                 │
┌────────────────────────────────────┐ │
│  PROMPT (prompt_llm)               │ │
│  units/canonical/prompt            │ │
│  template_path + data → system_prompt, user_message
└────────────────────────────────────┘ │
     │ system_prompt, user_message     │
     ▼                                 │
┌────────────────────────────────────┐ │
│  LLM AGENT (llm_agent)              │ │
│  units/env_agnostic/agents/llm_agent
│  system_prompt + user_message → LLM_integrations.client.chat() → action (raw text)
└────────────────────────────────────┘ │
     │ action ──────────────────────────► to caller (display)
     ▼
┌────────────────────────────────────┐
│  PARSER (parser) ProcessAgent      │
│  units/env_agnostic/process_agent │
│  action → parse_workflow_edits → edits (list)
└────────────────────────────────────┘
     │ edits
     ▼
┌────────────────────────────────────┐     graph ◄── inject_graph.data
│  PROCESS (process) ApplyEdits      │
│  units/env_agnostic/apply_edits   │
│  graph + edits → apply_workflow_edits → result, status
└────────────────────────────────────┘
     │ result, status ─────────────────► to caller (apply, toast, meta)
     ▼
  (ApplyEdits applies edits internally; no separate Router or Action units in this graph)
```

## Flow summary

| Stage        | Component   | Role |
|--------------|-------------|------|
| **Caller**   | Chat / runner | **Runs** the flow; **supplies** `initial_inputs[inject_*] = {"data": value}` for each Inject; **consumes** LLMAgent output (display), Process result + status (apply graph, toast, meta). Not a unit in the graph. |
| **Inject**   | 8 units     | One per source. No inputs from graph; data from `initial_inputs` at start. Output `data` → Merge in_0..in_6, or → Process (graph). |
| **Merge**    | merge_llm   | `units/canonical/merge`. in_0..in_6 → single `data` dict (keys: user_message, graph_summary, …). |
| **Prompt**   | prompt_llm  | `units/canonical/prompt`. data → system_prompt + user_message. |
| **LLMAgent** | llm_agent   | `units/env_agnostic/agents/llm_agent`. Calls `LLM_integrations.client.chat`. Output → caller + Parser. |
| **Parser**   | parser      | ProcessAgent. `parse_workflow_edits(action)` → edits list. |
| **Process**  | process     | ApplyEdits. graph (from inject_graph) + edits (from parser) → `apply_workflow_edits` → result, status. |

## Error and self-correction

When an apply fails, **Process** returns status (e.g. `error`, `success: false`) and the **caller** can store it (e.g. `last_apply_result`). On the **next** turn, the caller runs the flow again with updated `initial_inputs`, e.g.:

- `inject_last_edit_block`: `{"data": "<self-correction block and last error>"}`
- `inject_turn_state`: `{"data": "Last action: failed. …"}`

So the caller passes error and self-correction via the Inject units for the next run.

## Graph file

The pipeline is defined in **assistant_workflow.json**: Inject units (8) → Merge → Prompt → LLMAgent → ProcessAgent (parser) → ApplyEdits (process). The runner (`assistants/runner.run_assistant_workflow`) loads this graph, sets `initial_inputs` for each inject, runs the executor, and returns `response`, `result`, `status`.
