# Inject

Forwards data from the executor’s `initial_inputs` as a single output port `data`. No input ports from the graph; the backend supplies all data at run time. Env-agnostic; use for edit flows (graph), assistant flows (context per source), or subflows.

**Unit type:** `Inject`

## Purpose

Data for the flow is not always produced by an upstream node; the backend injects it when running the graph. This unit has no input ports from connections. The executor passes `initial_inputs[inject_unit_id] = { ... }`. The unit forwards that as output port `data` with one rule:

- If the payload has a key **`"data"`**, the output port `data` receives that value (so you can inject a single value: `initial_inputs["inject_foo"] = {"data": "hello"}` → downstream gets `"hello"`).
- Otherwise, the output port `data` receives the full payload (so you can inject a whole dict: `initial_inputs["inject"] = {"graph": {...}}` → downstream gets `{"graph": {...}}`).

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | —         | —    | None (all data comes from `initial_inputs`) |
| **Outputs**  | data      | Any  | Injected value: either `payload["data"]` if present, or the full `payload` |

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
