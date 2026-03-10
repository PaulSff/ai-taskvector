# Implementation checklist: assistant workflow

What to implement so the trigger (Chat) can run the full flow and consume response + result/status.

---

## 1. LLMAgent (call/response)

**Goal:** LLMAgent is executed by the graph; it calls the LLM client and outputs the raw response.

| Task | Details |
|------|---------|
| Implement LLMAgent `step_fn` | In `units/env_agnostic/agents/llm_agent.py`: replace the no-op with a step that reads `system_prompt` (and optionally `observation` / user message) from inputs, builds `messages`, calls `LLM_integrations.client.chat(provider=params["provider"], config={...}, messages=..., timeout_s=...)`, returns `{"action": response_text}`. Use unit `params` for model_name, provider, host (override from app_settings at runtime if desired). |
| Remove LLMAgent from executor exclude list | In `core/schemas/agent_node.py`: remove `LLM_AGENT_NODE_TYPES` from `EXECUTOR_EXCLUDED_TYPES` so the executor runs the LLMAgent unit. (Keep RLAgent, RLOracle, RLGym excluded if they still run via adapters.) |
| Port type for "action" | LLMAgent output is a string (raw response). Registry currently has `("action", "vector")`; consider changing to `("action", "Any")` or a string type so the executor and downstream units accept string. |

**Result:** Merge → Prompt → LLMAgent runs; LLMAgent outputs the assistant response string.

---

## 2. Parser as a unit

**Goal:** A unit that takes the LLM response (string) and outputs parsed edits (and optional request_file_content, rag_search, etc.).

| Task | Details |
|------|---------|
| Add ProcessAgent / Parser unit | New unit type (e.g. `ProcessAgent` or `ParseEdits`) in `units/` or `assistants/`. Input port: `action` (string, from LLMAgent). Output port: `edits` (Any: list of edit dicts or dict with `edits`, `request_file_content`, etc.). |
| step_fn | Call `assistants.process_assistant.parse_workflow_edits(inputs["action"])`; return `{"edits": parsed}` (or the full parse result dict). Handle string/None. |
| Register unit | Register in a central place so the assistant workflow graph can reference it (e.g. `type: "ProcessAgent"`). |

**Result:** LLMAgent → Parser; Parser outputs structured edits (and side channels) for Process.

---

## 3. Process as a unit

**Goal:** A unit that takes current graph + parsed edits, runs apply logic, and outputs result + status.

| Task | Details |
|------|---------|
| Add ApplyEdits / Process unit | New unit type (e.g. `ApplyEdits` or `ProcessEdits`). Input ports: `graph` (Any), `edits` (Any). Output ports: `out_1` result (content_for_display, graph, edits, kind), `out_2` status (apply_result: attempted, success, error). |
| step_fn | Get graph from inputs["graph"] (or from a dedicated inject); get edits from inputs["edits"]. Call `assistants.process_assistant.apply_workflow_edits(graph, edits, ...)` (with optional rag_index_dir, rag_embedding_model from params or env). Build result dict (kind, graph, content_for_display, edits) and apply_result (attempted, success, error); return `{"result": ..., "status": ...}` or two named outputs. |
| Graph input | Process needs the current graph. The **trigger** passes it via **initial_inputs["process"] = {"graph": current_graph}**. No inject unit needed: the executor merges initial_inputs per unit in `_build_inputs`; the core does not hold "the graph being edited" — only the workflow graph (Merge, Prompt, LLMAgent, …). |

**Result:** Parser → Process (edits); trigger supplies graph via initial_inputs to Process. Process → result + status (consumed by trigger).

---

## 4. Router as a unit

**Goal:** Route each edit to the right apply path. We decided to skip JSON edit workflows and call `apply_graph_edit` directly.

| Task | Details |
|------|---------|
| Option A – Router as explicit unit | Unit with input `edits` (list) and `graph`; output `graph`. step_fn: for each edit, `graph = apply_graph_edit(graph, edit)` (using `core.graph.graph_edits.apply_graph_edit`). Then Process could be “orchestrate + Router” or Router could sit between Parser and Process. |
| Option B – Router inside Process | Process unit internally loops over edits and calls `apply_graph_edit` (or `process_assistant_apply` → `apply_graph_edit`) per edit. No separate Router unit; Router is just the internal loop in Process. **Recommended** so the flow stays Merge → Prompt → LLMAgent → Parser → Process (graph from trigger via initial_inputs). |

**Result:** Either a separate Router unit (edits + graph → graph) or Process embeds the “router” logic (direct apply_graph_edit per edit). Recommendation: **Option B** (Process does parse + apply in one place; no separate Router unit in the graph).

---

## 5. Graph input to the flow

**Goal:** Process needs the current graph to apply edits. The **core/executor** is not aware of "the graph being edited" — it only runs the workflow graph and applies `initial_inputs` per unit. The trigger holds the current graph.

| Task | Details |
|------|---------|
| No inject unit | Pass the graph via **initial_inputs["process"] = {"graph": current_graph}**. The executor's `_build_inputs` merges initial_inputs for each unit, so Process will receive `graph` on its `graph` input port. No separate inject unit in the flow. |
| Process unit has "graph" input | Ensure the Process unit declares an input port `graph` (Any); the trigger supplies it when calling `execute(initial_inputs=...)`. |

**Result:** Trigger supplies current graph via initial_inputs to Process directly. No inject in the flow.

---

## 6. Trigger (runner) that runs the flow

**Goal:** Chat (or a headless runner) loads the workflow, supplies obs sources + graph, runs the executor, and consumes response + result/status.

| Task | Details |
|------|---------|
| Load assistant workflow | Load `assistant_workflow.json` (or path from config), normalize to ProcessGraph. |
| Build initial_inputs | (1) **Merge** inputs: map prompt template keys to values (user_message, graph_summary, units_library, rag_context, turn_state, recent_changes_block, last_edit_block). graph_summary = `graph_summary(current_graph)`; last_edit_block / turn_state from last_apply_result and self-correction template. (2) **Process** graph: initial_inputs["process"] = {"graph": current_graph}. No inject unit. |
| Run executor | `GraphExecutor(graph).execute(initial_inputs=initial_inputs)`. No injected_outputs needed once LLMAgent is run in-process. |
| Consume outputs | From executor outputs: (1) LLMAgent unit output["action"] = raw response string → display, pass to Parser (already in flow). (2) Process unit output["result"], output["status"] → apply graph if success, show toast, store last_apply_result, attach meta to message. |
| Override LLMAgent params from app_settings | When building the graph or before execute, set llm_agent.params from config (e.g. workflow_designer_ollama_model, workflow_designer_ollama_host, workflow_designer_llm_provider). |

**Result:** Caller uses **`runtime.run.run_workflow()`** (see `runtime/run.py`) with workflow path and `initial_inputs` built per inject (see ASSISTANT_WORKFLOW_README.md); from returned outputs, use `outputs["llm_agent"]["action"]` as response, `outputs["process"]["result"]` and `outputs["process"]["status"]` for apply/toast/meta.

---

## 7. assistant_workflow.json topology

**Goal:** The JSON describes the full flow so the executor can run it.

| Task | Details |
|------|---------|
| Add Parser unit | e.g. `{"id": "parser", "type": "ProcessAgent", ...}`. |
| Add Process unit | e.g. `{"id": "process", "type": "ApplyEdits", ...}` with input ports graph, edits. Graph supplied by trigger via initial_inputs["process"]["graph"]; no graph inject unit. |
| Connections | merge_llm → prompt_llm → llm_agent (existing). llm_agent → parser (action → action). parser → process (edits → edits). Remove or repurpose Switch. |
| Remove Switch or keep | Switch was LLMAgent → Switch; if we don’t need it, remove it and connect LLMAgent → Parser. |

**Result:** assistant_workflow.json defines Merge → Prompt → LLMAgent → Parser → Process, with graph_in → Process.

---

## 8. Optional / follow-ups

| Item | Details |
|------|---------|
| process_assistant_apply | Done: calls `apply_graph_edit` directly; `edit_workflow_runner` and `edit_workflows/` removed. |
| Prompt template | Ensure `config/prompts/workflow_designer.json` (or template_path in Prompt unit) exists and has the right placeholders for Merge keys. |
| User message into LLMAgent | LLMAgent needs system_prompt (from Prompt) and usually a user message. Either add an input port "user_message" and feed it from Merge (e.g. user_message from obs sources) or have the step_fn build messages from system_prompt + a single user content from params/inputs. |
| Streaming | If the trigger wants streaming display, the executor runs to completion; streaming would require the LLMAgent step_fn to stream (e.g. yield chunks) and the runner to consume them. For a first version, non-streaming (full response from LLMAgent) is enough. |

---

## Summary order

1. **LLMAgent (call/response)** – step_fn + stop excluding from executor.
2. **Parser unit** – new unit, parse_workflow_edits.
3. **Process unit** – new unit, apply_workflow_edits, two outputs (result, status).
4. **Router** – keep inside Process (no separate Router unit); Process loops and calls apply_graph_edit.
5. **Graph input** – no inject; trigger passes graph via initial_inputs["process"]["graph"].
6. **assistant_workflow.json** – add parser, process; wire LLMAgent → parser → process (graph from trigger).
7. **Trigger/runner** – build initial_inputs, execute(), consume LLMAgent output and Process result/status.
