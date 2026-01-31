# Environment / Process Assistant — Formal Approach

This document formalizes the **Environment / Process Assistant**: its role, input/output, recommended implementation (start with prompt-only; fine-tune later if needed), and integration with the constructor.

---

## 1. Role

The **Environment / Process Assistant** helps users (and the system) **design the process** without writing code:

- **Suggest or apply**: environment type (e.g. thermodynamic, chemical, robotics), which **units** to add (Source, Valve, Tank, Sensor, pipe, etc.), how to **connect** them, and **bounds** (pressure, temperature, flow).
- **Operates on**: process graph and env config (YAML/JSON), **not** Python source.
- **Does not**: write `temperature_env.py` or edit `step()`; it only proposes or applies **declarative edits** to the process graph.

---

## 2. Input and Output

| | Description |
|---|-------------|
| **Input** | User message (natural language) + **current process graph** (and optionally env type, unit library summary). Example: "Add a second tank after the mixer" + current graph JSON. |
| **Output** | (1) **Natural language response** (explanation, confirmation). (2) **Structured edit** to the process graph: e.g. `{"action": "add_unit", "unit": {...}}` or full updated graph snippet. The backend applies the edit to the graph; the constructor (e.g. Node-RED) or API persists it. |

The assistant **never** outputs raw code; it outputs **graph edits** (add/remove/connect units, change params) in a defined schema.

---

## 3. Recommended Approach: Start with Prompt-Only, Fine-Tune Later

**Do not train from scratch.** Use an **existing open-source LLM** and steer it with prompts (and optional RAG). Fine-tune only if accuracy is insufficient.

### 3.1 Why not train from scratch?

- Expensive and unnecessary: base LLMs already have strong instruction-following and reasoning.
- Small datasets for "process graph editing" are easier to use for **fine-tuning** than for training from scratch.
- Faster to iterate with **prompt + structured output** first; collect (user request, correct edit) pairs from usage, then fine-tune if needed.

### 3.2 Best option to start: Prompt-only + structured output

| Step | What to do |
|------|-------------|
| **Base model** | Use an **existing open-source LLM** via **Ollama** (e.g. Llama 3.2 3B, Mistral 7B, Qwen2.5 7B) or another local/cloud API. No training. |
| **System prompt** | Define the assistant's role, **environment types** (thermodynamic, chemical, etc.), **unit library** (Source, Valve, Tank, Sensor, connection rules), and **output format** (JSON for graph edits). See §5. |
| **Few-shot examples** | Include 1–3 examples in the prompt: user request → assistant reply + structured edit (e.g. add unit, connect A to B). |
| **Structured output** | Require the model to output a **JSON block** for the edit (e.g. `{"intent": "add_unit", "unit": {"id": "...", "type": "Valve", ...}}`). Parse this in the backend and apply to the graph. |
| **Optional RAG** | If the unit library or connection rules are large, index them (e.g. Markdown/JSON docs) and **retrieve** relevant snippets by user query; inject into the prompt. Improves accuracy without fine-tuning. |

### 3.3 When to fine-tune

- **Fine-tune later** if: (1) prompt-only gives wrong units or invalid connections often, or (2) you need consistent output schema compliance (e.g. JSON always valid).
- **How**: Collect (user message, current graph, correct graph edit) from usage or synthetic data. Fine-tune a **small** model (e.g. Llama 3.2 3B, Qwen2.5-7B) with **LoRA/QLoRA** for the task "given user message + graph → output graph edit (JSON)." Keep the same input/output schema as in this doc.

---

## 4. What You Implement (No New Model Training to Start)

| Component | Description |
|-----------|-------------|
| **System prompt** | Text that defines: role, env types, unit library, connection rules, output JSON schema. |
| **Few-shot examples** | 1–3 (user request → response + JSON edit) in the prompt or retrieved by RAG. |
| **Structured output parser** | Parse the model reply for a JSON block (e.g. between ` ```json ` and ` ``` `); validate against schema; apply edit to process graph. |
| **Graph edit API** | Backend that receives the parsed edit and applies it to the process graph (add/remove/connect units, update params). Constructor (Node-RED) or API then persists the updated graph. |
| **Optional RAG** | Index: unit types, connection rules, example graphs. Retrieve by query; add to prompt. |

---

## 5. System Prompt Outline (Process Assistant)

Use this as a template; customize env types and units to your app.

```text
You are the Environment / Process Assistant. You help users design process environments (e.g. thermodynamic: pipelines, valves, tanks, sensors) by suggesting or applying edits to the process graph. You never write code; you only output structured edits (JSON).

## Environment types
- thermodynamic: pipelines, valves, tanks, pressure, thermometers, barometers
- chemical: reactors, separation, streams (IDAES-style)
- generic_control: CSTR, first-order systems (PC-Gym style)

## Unit library (thermodynamic)
- Source: id, type=Source, params={ temp, max_flow }
- Valve: id, type=Valve, controllable=true|false
- Tank: id, type=Tank, params={ capacity, cooling_rate }
- Sensor: id, type=Sensor, measure=temperature|pressure|...

## Connection rules
- Source → Valve → Tank; Tank → Valve (dump); Tank → Sensor (measurement)
- Only connect compatible outlets to inlets (e.g. flow to flow).

## Output format
Always end your reply with a JSON block for the edit, inside ```json ... ```:
- add_unit: { "action": "add_unit", "unit": { "id": "...", "type": "...", "params": {...} } }
- remove_unit: { "action": "remove_unit", "unit_id": "..." }
- connect: { "action": "connect", "from": "unit_id", "to": "unit_id" }
- disconnect: { "action": "disconnect", "from": "unit_id", "to": "unit_id" }
- no_edit: { "action": "no_edit", "reason": "..." }

If the user message does not request a graph change, output { "action": "no_edit", "reason": "..." } and explain in natural language.
```

---

## 6. Output Schema (Graph Edit)

The assistant's **structured output** (parsed from the model reply) should match one of the following (validate in backend):

```json
{
  "action": "add_unit" | "remove_unit" | "connect" | "disconnect" | "no_edit",
  "unit_id": "optional for remove_unit",
  "unit": { "id": "...", "type": "Source|Valve|Tank|Sensor", "params": {} },
  "from": "unit_id for connect/disconnect",
  "to": "unit_id for connect/disconnect",
  "reason": "optional for no_edit"
}
```

The backend maps these to concrete changes in the process graph (YAML/JSON); the constructor or API persists the result.

---

## 7. Base Model Suggestion (Start)

| Option | Model | Use case |
|--------|-------|----------|
| **Local (Ollama)** | Llama 3.2 3B, Mistral 7B, Qwen2.5-7B | No API keys; good for prototyping and offline use. |
| **Larger local** | Llama 3.1 8B, Qwen2.5-14B | If 3B/7B underperforms on complex graphs. |
| **Cloud** | OpenAI GPT-4o-mini, Claude Haiku, etc. | If you need best quality and accept API cost. |

Start with **Ollama + Llama 3.2 3B or Mistral 7B**; same stack as your model-operator (chat_with_local_ai.py). Upgrade or fine-tune only if needed.

---

## 8. Integration with Constructor

- **Node-RED**: When the user asks the Process Assistant (e.g. in a chat panel), your backend calls the LLM with (user message + current Node-RED flow JSON or converted process graph). Backend parses the JSON edit, applies it to the **process graph** representation, then either (1) exports updated flow JSON for Node-RED to load, or (2) sends edits via Node-RED API if available.
- **Custom GUI**: Same: backend receives user message + current graph, calls LLM, parses edit, applies to graph, returns updated graph to front-end.

---

## 9. Summary

| Question | Answer |
|----------|--------|
| **Train from scratch?** | No. Use an existing open-source LLM (Ollama: Llama, Mistral, Qwen). |
| **Fine-tune from the start?** | No. Start with **prompt-only + structured output** (system prompt + few-shot + JSON schema). |
| **When to fine-tune?** | When prompt-only is not accurate or consistent enough; then fine-tune a small model (LoRA) on (user message, graph, correct edit) pairs. |
| **Best option to start** | **Prompt-only + structured output** with Ollama (Llama 3.2 3B or Mistral 7B) + system prompt (§5) + output schema (§6) + graph edit API. Optional RAG over unit library and connection rules. |

This keeps the Environment / Process Assistant **simple to start** and **easy to improve** later with RAG or fine-tuning.
