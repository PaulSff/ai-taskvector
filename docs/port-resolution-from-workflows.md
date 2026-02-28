# Port resolution from imported workflows

Port semantics (names, types, count) are **not** fully derivable from the workflow JSON alone in either Node-RED or n8n. Deterministic logic on the raw workflow is insufficient.

## Why it’s underdetermined

- **n8n**: The workflow does not declare port count or available ports per node. Only `connections` show which port types are *used*. Full inputs/outputs are in the node type (e.g. `.node.ts` `INodeTypeDescription.inputs` / `outputs`).
- **Node-RED**: The workflow declares *output count* via `wires.length` (and subflow `in`/`out`), but not port *names* or semantics. Those come from the node definition (e.g. `.html` `inputLabels`/`outputLabels`) or convention (e.g. msg).

So: **workflow → node type lookup → node spec → ports for units**.

## Spec sources are unstructured

There is **no single, well-structured spec format**. Port and semantic information is spread across:

| Source | What it contains | Structured? |
|--------|-------------------|-------------|
| **Node-RED .html** | `RED.nodes.registerType(type, { inputs, outputs, inputLabels?, outputLabels? })` — the only machine-parseable port *structure*. Plus help script (prose). | Partially: counts and sometimes labels in JS object; help is prose. |
| **Node-RED README** | Package description, install, usage (e.g. “Requires msg.payload to be 'r,g,b'”). | No — prose. |
| **Node-RED .js** | Runtime: `on("input", ...)`, `node.send(...)`. Confirms port count and data flow; no formal “spec” declaration. | No — code. |
| **package.json** | Module name, node-red.nodes mapping (which .js). No port info. | N/A. |

Example (digiRGB): HTML has `inputs:1, outputs:0`; no inputLabels/outputLabels. Help says “Expects msg.payload with r,g,b”. README says same. JS implements `on("input", ...)` and `msg.payload`. So **structure** (count) is only in HTML; **semantics** (what the port carries) are in prose and code.

So we are dealing with **mostly unstructured information** — prose and code, plus one semi-structured slice (the registerType object in HTML). That makes an **LLM a good fit** for resolving “what are the inputs/outputs for this node type?” from that mix.

## Indexing for LLM: HTML + README vs. code as well

- **HTML + README (and in-HTML help)**  
  - HTML gives: port count and, when present, inputLabels/outputLabels; plus help text in `data-help-name` script.  
  - README gives: package-level description and usage.  
  - For many nodes this is **sufficient** for the LLM to answer “inputs/outputs and basic semantics” (e.g. “1 input, 0 outputs; input is msg.payload (r,g,b or hex)”).

- **Index code as well when**  
  - Labels are missing and we need to infer from implementation (e.g. multiple `node.send()` paths → multiple outputs).  
  - README/help are sparse and the only description of behavior is in the .js.  
  - We want the LLM to disambiguate or explain behavior, not just port list.

**Recommendation:** Index **HTML and READMEs** (and in-HTML help) as the default for Node-RED port resolution; add **code** to the index when we need to infer or disambiguate, or when building a richer “node behavior” summary.

## Task

1. **Read the workflow** (nodes, connections, and any port-related fields).
2. **Find and learn node semantics** from the appropriate spec source (unstructured: HTML, README, help; optionally code; n8n: .node.ts or registry).
3. **Set up ports available for the units** using that spec (e.g. store in origin or in a resolved view so graph summary / executor / UI see consistent port names and count).

Implementation can be: a **port-resolution layer** that runs after normalizer (or as part of it), uses an **index of node spec sources** (HTML, README, optionally code) and **LLM** to resolve port lists from that unstructured mix, and attaches or exposes per-unit port lists; fallbacks (convention, or deterministic parse of HTML when possible) when LLM is not used or type is still unknown.

**n8n:** For a short summary of n8n node structure, connection types (`main`, `ai_*`), workflow JSON format, and where port specs live, see **`docs/n8n-conventions.md`**. Use it as the primary convention reference for n8n port resolution; node types are defined in `.node.ts` under `mydata/n8n/nodes/`.

---

## Node-RED: summary vs index for LLM

**Option A — Summary only**  
Use a single **Node-RED-conventions.md** (see `docs/Node-RED-conventions.md`) as the document the LLM "checks" for msg, payload, port model, and where ports are declared. Small, consistent, low token cost.

**Option B — Index everything**  
Index all of `mydata/node-red/docs` (and node .html/README). Retrieval surfaces whatever matches; no separate summary to maintain, but the LLM may get noisy or redundant chunks (getting-started, faq, etc.) unless we filter or rank.

**Recommended — Both**  
1. **Primary convention check**: Give (or retrieve) **Node-RED-conventions.md** when the task is "resolve Node-RED node ports." One place, fast, consistent.  
2. **Index**: Index the conventions summary **and** the full docs (and node .html/README). Use the summary as the default convention reference; when the LLM needs detail or a specific node, retrieval can pull the full doc or node content. Optionally restrict indexing to the "useful for conventions" paths below so retrieval stays relevant.

So: **keep the summary** (`docs/Node-RED-conventions.md`) for the LLM to check; **index that plus the key docs and nodes**; use the summary first, full docs/nodes when needed.

---

## Node-RED docs useful for LLM (conventions: msg, payload, ports)

**First:** `docs/Node-RED-conventions.md` — short summary of msg, payload, port model, registerType, help structure.

**Full docs** under `mydata/node-red/docs` (for indexing or when the LLM needs more detail):

| Doc | Use for LLM |
|-----|--------------|
| **user-guide/concepts.md** | Core concepts: Node (at most one input, many outputs), Message (`msg`), Wire, Flow, Subflow. Defines that messages are JS objects, often with `payload`. |
| **user-guide/messages.md** | Message model: `msg` object, `payload` as default property, `_msgid`; changing properties (Change node); `msg.topic`; message sequences and `msg.parts`. |
| **user-guide/writing-functions.md** | Function node: `msg` in/out, `return msg`, multiple outputs as `return [msg, null]`; `node.send()`; convention that `msg` carries the message. |
| **developing-flows/message-design.md** | Design of messages: `msg.payload` as default; `msg.topic`; principle that nodes should not strip unrelated properties; avoiding reserved names (`reset`, `parts`). |
| **creating-nodes/node-html.md** | Where port *structure* is declared: `inputs` (0 or 1), `outputs` (0 or more), `inputLabels`, `outputLabels` in `RED.nodes.registerType(type, { ... })`; edit template and help script. |
| **creating-nodes/node-js.md** | Runtime: `this.on('input', function(msg, send, done) { ... })`; `this.send(msg)`; multiple outputs via `send([msg1, msg2])`; confirms one input, N outputs, and that the single input is “the message” (`msg`). |
| **creating-nodes/help-style-guide.md** | How node help documents inputs/outputs: `<h3>Inputs</h3>`, `<dl class="message-properties">` (payload, topic, etc.), `<h3>Outputs</h3>`, `<ol class="node-ports">` for multiple outputs; so the LLM knows how to interpret help text in node .html. |

**Optional / supporting:** `user-guide/nodes.md` (core nodes and typical payload/topic usage), `user-guide/context.md` (context vs message), `creating-nodes/first-node.md` (minimal node example). **Lower priority for port/convention resolution:** getting-started, faq, tutorials, packaging, appearance, credentials.
