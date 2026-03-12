# Inject

Forwards data from the executor’s `initial_inputs` as a single output port `data`. No input ports from the graph; the backend supplies all data at run time. Canonical (native runtime only). Use for edit flows (graph), assistant flows (context per source), or subflows.

**Unit type:** `Inject`

## Purpose

Data for the flow is not always produced by an upstream node; the backend injects it when running the graph. The executor passes `initial_inputs[inject_unit_id] = { ... }`. Optional **`template`** input: wire a **Template** unit here; when the runner does not provide `"data"`, the Inject outputs the Template value (debug default).

- If the payload has **`"data"`** (from initial_inputs), output = that value.
- Else if a **Template** is connected to the `template` input, output = Template value.
- Otherwise output = full payload.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | template  | Any  | Optional. When connected to a Template, used as default when initial_inputs do not provide `data`. |
| **Outputs**  | data      | Any  | Injected value: `payload["data"]`, or `template` input, or full `payload` |

## Usage patterns

**Single-value inject (e.g. one source per Inject → Merge):**  
`initial_inputs["inject_user_message"] = {"data": "Add a valve"}`  
→ Output port `data` = `"Add a valve"`. Wire `inject_user_message.data` → `merge.in_0`, etc.

**Full payload (e.g. edit flow graph):**  
`initial_inputs["inject"] = {"graph": {"units": [...], "connections": [...]}}`  
→ Output port `data` = `{"graph": {"units": [...], "connections": [...]}}`. Downstream reads `data["graph"]`.

**Arbitrary dict:**  
`initial_inputs["inject"] = {"user_message": "...", "history": []}`  
→ Output port `data` = that dict. Downstream uses keys as needed.

Downstream units connect to the `data` output and use the value or dict as needed.
