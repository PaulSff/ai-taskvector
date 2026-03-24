# ValidateGraphToApply

Canonical unit that **validates** a process graph against the **`ProcessGraph`** schema (`core.schemas.process_graph`) and returns a **canonical dict** (field names as JSON aliases, same shape as `model_dump(by_alias=True)`).

Use it anywhere you have a loose dict or a Pydantic-like object from JSON, edits, or another unit and need a schema-checked graph for downstream steps.

## Inputs

| Port   | Type | Description |
|--------|------|-------------|
| `graph` | `Any` | Required for success. A **`dict`** (typical JSON graph) or any object with **`model_dump`** (e.g. a `ProcessGraph` instance). If missing, outputs fail as below. |

## Outputs

| Port    | Type  | Description |
|---------|-------|-------------|
| `graph` | `Any` | On success: validated graph as a **dict** (`by_alias=True`). On failure: **`None`**. |
| `error` | `str` | On success: **`None`**. On failure: short message (capped, e.g. missing input, wrong type, or Pydantic validation error). |

## Behavior

- **`graph` is `None`:** `graph` out is `None`, `error` explains missing input.
- **Not a dict and no `model_dump`:** validation fails with a type error.
- **`model_dump` present:** dumps with `by_alias=True` and validates the resulting dict.
- **Pydantic / schema errors:** caught; `graph` is `None`, `error` summarizes the exception.

## Params

None.

## Environment

`environment_tags_are_agnostic=True` — no environment binding required.

## Example wiring

Pair with **Inject** in a single-step workflow: inject payload key `graph` → **ValidateGraphToApply** → read `graph` / `error`. Any caller (CLI, GUI, tests, other workflows) can run the same workflow or invoke the registered unit directly.
