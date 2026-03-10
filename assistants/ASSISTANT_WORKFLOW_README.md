# Assistant workflow (assistant_workflow.json)

Defines the process graph for the Workflow Designer assistant:

**Inject (per source) → Merge → Prompt → LLMAgent → ProcessAgent (parser) → ApplyEdits (process)**

Chat (or any caller) is not in the graph; it runs the flow, supplies data via `initial_inputs` to each Inject, and consumes response, result, and status.

## Topology

| Unit                      | Type        | Role |
|---------------------------|-------------|------|
| inject_user_message       | Inject      | Source: user message. Output `data` → merge_llm.in_0. |
| inject_graph_summary      | Inject      | Source: graph summary dict. → merge_llm.in_1. |
| inject_units_library      | Inject      | Source: units library string. → merge_llm.in_2. |
| inject_rag_context        | Inject      | Source: RAG context. → merge_llm.in_3. |
| inject_turn_state         | Inject      | Source: turn state line. → merge_llm.in_4. |
| inject_recent_changes_block | Inject    | Source: recent changes text. → merge_llm.in_5. |
| inject_last_edit_block    | Inject      | Source: self-correction block (e.g. after failed apply). → merge_llm.in_6. |
| inject_graph              | Inject      | Source: current graph (dict). Output `data` → process.graph. |
| merge_llm                 | Merge       | Collects in_0..in_6 into one `data` dict (keys: user_message, graph_summary, …). |
| prompt_llm                | Prompt      | Builds system_prompt + user_message from `data` (template: `config/prompts/workflow_designer.json`). |
| llm_agent                 | LLMAgent    | Calls LLM; params (model_name, provider, host) overridable via runner. |
| parser                    | ProcessAgent| Parses LLM output → edits list. |
| process                   | ApplyEdits  | Applies edits to graph; outputs result, status. |

## Initial inputs (runner)

The runner sets **one Inject per source**. For each inject unit id, it passes `initial_inputs[id] = {"data": value}`:

| Inject id                   | value |
|-----------------------------|--------|
| inject_user_message        | User message string. |
| inject_graph_summary       | Current graph summary (dict). |
| inject_units_library       | Formatted units library string. |
| inject_rag_context        | RAG snippets (or ""). |
| inject_turn_state         | Turn state line (e.g. "Last action: none."). |
| inject_recent_changes_block | Recent changes text (or ""). |
| inject_last_edit_block    | Self-correction block if last apply failed (or ""). |
| inject_graph              | Current process graph (dict) to apply edits to. |

Merge `params.keys` order must match the wiring: in_0 = user_message, in_1 = graph_summary, … in_6 = last_edit_block.

## LLMAgent params

At runtime the runner may override `llm_agent.params` (e.g. from `config/app_settings.json` or `llm_params_override`):

- workflow_designer_ollama_model → model_name  
- workflow_designer_llm_provider → provider  
- workflow_designer_ollama_host → host  

## Outputs

- **response**: LLMAgent output (raw text) for display.
- **result**: ApplyEdits result (kind, content_for_display, graph, edits, last_apply_result).
- **status**: ApplyEdits status (attempted, success, error, edits_summary).

Edit parsing and application are done inside the Process (ApplyEdits) unit; the caller uses result and status to update the UI and optionally retry with updated inject values (e.g. last_edit_block).
