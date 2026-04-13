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
          "run_workflow": { "path": "rag/workflows/doc_to_text.json" }
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

Inner graphs can set **`run_workflow.unit_param_overrides`** (same shape as `runtime.run.run_workflow`) so nested units (e.g. `format_rag` / `rag_filter`) get merged params without duplicating the child workflow file. Extra Inject wiring still uses `initial_inputs` in the payload or parent `initial_inputs`.

## `params.repeat_for_each` (list expansion)

When **`params.repeat_for_each`** is an object with **`field`** and **`item_template`**, **PayloadTransform** ignores **`routes`** and instead:

1. Reads **`data[field]`** (must be a list; coerced to `[]` if missing or wrong type).
2. For each element **`el`**, builds a shallow copy of **`data`** with **`merge_key`** (default `path`) set to **`el`**.
3. Runs the same placeholder substitution as **`routes`**, on **`item_template`**, against that merged dict.
4. Emits **`parser_output`** = **`{ output_key: [ … built items … ] }`** where **`output_key`** defaults to **`actions`** (e.g. for **Chameleon**).

| Key | Default | Description |
|-----|---------|-------------|
| **field** | (required) | Dot path on **`data`** to the list to iterate (e.g. `implementation_source_paths`). |
| **item_template** | (required) | Dict/list to substitute per item (use `{path}` or `{merge_key}` if `merge_key` is not `path`). |
| **merge_key** | `path` | Name merged into the per-item copy of **`data`** for placeholders. |
| **output_key** | `actions` | Key wrapping the built list on **`parser_output`**. |

## Pipeline pattern

**Router** (optional fan-out) → **PayloadTransform** (per branch, different `params.routes`) → **RunWorkflow**.
