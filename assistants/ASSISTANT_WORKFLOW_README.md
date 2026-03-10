# Assistant workflow (assistant_workflow.json)

Defines the process graph for the Workflow Designer assistant:

**Inject (per source) + UnitsLibrary + (User message → RagSearch → Filter → FormatRagPrompt) → Merge → Prompt → LLMAgent → ProcessAgent (parser) → ApplyEdits (process)**

The **UnitsLibrary** unit takes `graph_summary` (from `inject_graph_summary`) and outputs the filtered units list. RAG context is built by **inject_user_message → RagSearch → Filter (data_bi, score ≥ 0.48) → FormatRagPrompt → Merge** (rag_context key). Callers do not inject units_library or rag_context. Pass `unit_param_overrides={"rag_search": {"persist_dir": "...", "embedding_model": "..."}}` when running the workflow (e.g. from GUI settings). Chat runs the flow via **`runtime.run.run_workflow()`** (see `runtime/run.py`), supplies data via `initial_inputs` to each Inject, and consumes response, result, and status.

## How to run

Use the generic runner in **`runtime/run.py`**:

```python
from runtime.run import run_workflow
from assistants.process_assistant import graph_summary

path = "assistants/assistant_workflow.json"
# Build initial_inputs per inject (see table below)
current_graph = {"units": [], "connections": []}  # or your graph dict
initial_inputs = {
    "inject_user_message": {"data": user_message},  # also feeds RagSearch → Filter → FormatRagPrompt → Merge
    "inject_graph_summary": {"data": graph_summary(current_graph)},  # also feeds UnitsLibrary → Merge
    "inject_turn_state": {"data": turn_state},
    "inject_recent_changes_block": {"data": recent_changes_block},
    "inject_last_edit_block": {"data": last_edit_block},
    "inject_graph": {"data": current_graph},
}
unit_param_overrides = {
    "llm_agent": {"model_name": "...", "provider": "...", "host": "..."},
    "rag_search": {"persist_dir": "/path/to/rag_index", "embedding_model": "sentence-transformers/all-MiniLM-L6-v2"},  # required for RAG
}  # optional

outputs = run_workflow(path, initial_inputs=initial_inputs, unit_param_overrides=unit_param_overrides, format="dict")

response = outputs.get("llm_agent", {}).get("action", "")
result = outputs.get("process", {}).get("result", {})
status = outputs.get("process", {}).get("status", {})
```

From the CLI: `python -m runtime assistants/assistant_workflow.json --format dict --initial-inputs @inputs.json`

## Topology

| Unit                      | Type        | Role |
|---------------------------|-------------|------|
| inject_user_message       | Inject      | Source: user message. → merge_llm.in_0 and → rag_search. |
| inject_graph_summary      | Inject      | Source: graph summary dict. → merge_llm.in_1 and → units_library. |
| units_library             | UnitsLibrary| graph_summary → formatted units list. Output `data` → merge_llm.in_2. |
| rag_search                | RagSearch   | query → RAG index results (table). Params: persist_dir, embedding_model. → rag_filter. |
| rag_filter                | Filter      | data_bi: table, score ≥ 0.48 → filtered table. → format_rag. |
| format_rag                | FormatRagPrompt | table → formatted "Relevant context..." block. Output `data` → merge_llm.in_3. |
| inject_turn_state         | Inject      | Source: turn state line. → merge_llm.in_4. |
| inject_recent_changes_block | Inject    | Source: recent changes text. → merge_llm.in_5. |
| inject_last_edit_block    | Inject      | Source: self-correction block (e.g. after failed apply). → merge_llm.in_6. |
| inject_graph              | Inject      | Source: current graph (dict). Output `data` → process.graph. |
| merge_llm                 | Merge       | Collects in_0..in_6 into one `data` dict (keys: user_message, graph_summary, …). |
| prompt_llm                | Prompt      | Builds system_prompt + user_message from `data` (template: `config/prompts/workflow_designer.json`). |
| llm_agent                 | LLMAgent    | Calls LLM; params (model_name, provider, host) overridable via runner. |
| parser                    | ProcessAgent| Parses LLM output → edits list. |
| process                   | ApplyEdits  | Applies edits to graph; outputs result, status, graph. |
| merge_response            | Merge       | Collects reply, result, status, graph, diff → single `data` dict for the GUI. |

## Initial inputs

The caller sets **one Inject per source** when calling `run_workflow()`. **UnitsLibrary** and the RAG chain (RagSearch → Filter → FormatRagPrompt) get inputs from the graph. Pass `unit_param_overrides["rag_search"] = {"persist_dir": ..., "embedding_model": ...}` so RAG search can run. For each inject unit id, pass `initial_inputs[id] = {"data": value}`:

| Inject id                   | value |
|-----------------------------|--------|
| inject_user_message        | User message string. Feeds Merge and RagSearch. |
| inject_graph_summary       | Current graph summary (dict). Feeds Merge and UnitsLibrary. |
| inject_turn_state         | Turn state line (e.g. "Last action: none."). |
| inject_recent_changes_block | Recent changes text (or ""). |
| inject_last_edit_block    | Self-correction block if last apply failed (or ""). |
| inject_graph              | Current process graph (dict) to apply edits to. |

Merge `params.keys` order must match the wiring: in_0 = user_message, in_1 = graph_summary, … in_6 = last_edit_block.

## LLMAgent params

At runtime the caller may pass `unit_param_overrides={"llm_agent": {...}}` to `run_workflow()` to override `llm_agent.params` (e.g. from `config/app_settings.json` or `llm_params_override`):

- workflow_designer_ollama_model → model_name  
- workflow_designer_llm_provider → provider  
- workflow_designer_ollama_host → host  

## Outputs

The workflow has a **response Merge** unit (`merge_response`) that collects all GUI-facing outputs into one dict. The GUI should read **one object**:

```python
response = outputs.get("merge_response", {}).get("data", {})
reply   = response.get("reply")   # LLM output (raw text) for display
result  = response.get("result")  # ApplyEdits result (kind, graph, edits, last_apply_result, ...)
status  = response.get("status")  # ApplyEdits status (attempted, success, error, edits_summary)
graph   = response.get("graph")   # Updated graph (when applied)
diff    = response.get("diff")    # GraphDiff output for next turn's inject_recent_changes_block
```

So the GUI only depends on `outputs["merge_response"]["data"]` and the keys above; it does not need to know unit IDs for llm_agent, process, or graph_diff.

---

## Standalone web flows (GUI-handled)

When the Workflow Designer LLM returns a **web_search** or **browse** action, the GUI runs one of two small workflows instead of calling unit helpers directly:

| File | Flow | initial_inputs | Output to read |
|------|------|----------------|----------------|
| **web_search.json** | Inject → web_search (one unit) | `{"inject_query": {"data": "<query>"}}` | `outputs["web_search"]["out"]` |
| **browser.json** | Inject → browser → beautifulsoup | `{"inject_url": {"data": "<url>"}}` | `outputs["beautifulsoup"]["out"]` |

The runner must call **`register_web_units()`** (from `units.web`) before `run_workflow()` so that `web_search`, `browser`, and `beautifulsoup` unit types are registered. Optional deps: `duckduckgo-search`, `requests`, `beautifulsoup4`.
