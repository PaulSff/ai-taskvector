# lookup_graph_units

Canonical unit that **looks up units by id** on a process graph and reports how they relate to **graph `code_blocks`**.

Logic lives in **`core.graph.lookup_units`** (`lookup_graph_units_data`); this unit only coerces inputs and calls that helper.

## Inputs

| Port | Type | Description |
|------|------|-------------|
| **graph** | Any | Graph dict (prefer output of **NormalizeGraph**) or object with `model_dump`. |
| **ids** | Any | Unit ids: `list[str]`, a single `str`, or a `dict` with `unit_ids`, `read_code_block_ids`, or `ids`. |

## Output

| Port | Type | Description |
|------|------|-------------|
| **data** | dict | Structured lookup |

### `data` fields

| Field | Type | Meaning |
|--------|------|---------|
| **unit_ids** | `list[str]` | Normalized ids passed in (order preserved, stripped strings). |
| **has_graph** | `bool` | `True` when the graph dict is non-empty and has a `units` key that is a list. |
| **code_block_ids** | `list[str]` | Sorted ids taken from `graph["code_blocks"][*].id` (each code block whose id is set). |
| **units** | `list[dict]` | One row per requested id: **`unit_id`**, **`found`** (unit exists in `graph["units"]`), **`has_code_block`** (that id appears in **code_block_ids**), **`unit_type_raw`**, **`unit_type_canonical`** (after `_canonical_unit_type`). |
| **canonical_types_without_code_block** | `list[str]` | Unique canonical types, in request order, for requested units that **exist** on the graph, **lack** a matching code block id, and have a non-empty canonical type. |
| **needs_implementation_links** | `bool` | `True` iff **canonical_types_without_code_block** is non-empty (e.g. drive Units Library / RAG in follow-ups). |

## Params

None.

## Wiring

Typical: **ValidateGraphToApply** → `graph`, **Inject** meta → `ids`, then **Router** / follow-up workflows (e.g. `assistants/tools/read_code_block/read_code_block_follow_up_workflow.json`).
