# PayloadTransform

Maps **`data`** → **`parser_output`** so downstream units (especially **`RunWorkflow`**) see the shape they already expect.

## Ports

| Direction | Name | Type |
|-----------|------|------|
| Input | **data** | Any |
| Output | **parser_output** | Any (normally a dict) |

If **data** is missing (no wire from an active branch), the unit outputs ``{"parser_output": {}}`` so downstream **RunWorkflow** no-ops instead of emitting a template with empty placeholders.

## `params.routes`

Ordered list of route objects (same matching idea as **Router**):

- **`all`**: list of rule dicts — every rule must match (AND).
- **`any`**: list of rule dicts — at least one must match (OR). Use when `all` is absent or empty.
- **`parser_output`**: template object (usually dict). After a route wins, placeholders in **strings** are substituted (see below).
- **`default`**: if `true`, this route applies only when **no** earlier route matched. At most one default; it should include **`parser_output`**.

A route with no `all`/`any` (and not `default`) never matches.

Rule dicts use the same keys as **Router** (`field`, `equals`, `equals_str`, `ends_with`, `starts_with`, `contains`, `regex`, `exists`).

## Placeholders

In any **string** value inside `parser_output`, `"{path}"` is replaced by the string form of `_get_field(data, "path")` (dot paths). Missing fields become `""`. Dict/list values are JSON-encoded when substituted into a string.

## Example: xlsx → `doc_to_text` path, else run current graph

```json
{
  "type": "PayloadTransform",
  "params": {
    "routes": [
      {
        "all": [{ "field": "path", "ends_with": ".xlsx" }],
        "parser_output": {
          "run_workflow": { "path": "gui/flet/components/workflow/assistants/doc_to_text.json" }
        }
      },
      {
        "default": true,
        "parser_output": { "run_workflow": {} }
      }
    ]
  }
}
```

Wire **`parser_output`** → **`RunWorkflow`**’s `parser_output` input; wire **`graph`** into `RunWorkflow` as today.

Inner graphs that need extra Inject wiring (e.g. `inject_path`) are unchanged: handle outside this unit (`runtime.run.run_workflow` with `unit_param_overrides`, or graph design), not via `RunWorkflow` payload extensions.

## Pipeline pattern

**Router** (optional fan-out) → **PayloadTransform** (per branch, different `params.routes`) → **RunWorkflow**.
