# Template

**Unit type:** `Template`

Outputs a fixed value from the **`data`** parameter. No input ports; no `initial_inputs` required. Use for debugging (e.g. hardcode a user message or minimal graph) or for static data in a workflow.

| **Params** | data | Any | Value to output on port `data`. |
| **Outputs** | data | Any | Same as `params["data"]`. |

**Example (debug):** In the workflow JSON, add a Template unit and wire it to the same target as an Inject (e.g. Merge). Set `params.data` to a string or dict; that value is used when the graph runs without supplying `initial_inputs` for the Inject.

```json
{
  "id": "template_user_message",
  "type": "Template",
  "params": { "data": "Add a single node" },
  "input_ports": [],
  "output_ports": [{ "name": "data", "type": "Any" }]
}
```

Wire `template_user_message.data` → `merge_llm.in_0` (or leave Inject wired and add Template as an alternative branch for debug runs).
