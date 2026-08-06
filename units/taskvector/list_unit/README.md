# list_unit

Scaffolds a new unit package under `units/<environment>/` and registers it in `UNIT_REGISTRY`. The Python implementation is taken from the **`source`** field of the graph **`code_blocks`** entry whose **`id`** matches **`code_block_id`**.

## Inputs (ports)

| Port | Type | Description |
|------|------|-------------|
| `data` | dict | **Required.** See shape below. |
| `graph` | Any | Process graph (`ProcessGraph` or dict) containing `code_blocks`. |

### `data` dict shape

| Key | Required | Description |
|-----|----------|-------------|
| `action` | yes | Must be `"list_unit"`. |
| `environment` | yes | Environment tag from `known_environment_tags()` (e.g. `data_bi`, `thermodynamic`). |
| `new_unit_type` | yes | `UnitSpec.type_name` (e.g. `MyFilter`). |
| `code_block_id` | yes | `id` of a `CodeBlock` on `graph.code_blocks`; that block’s `source` becomes `<snake>.py` (see below). |
| `readme_md` | no | Body written to `units/<env>/<snake>/README.md`. |

## Code block `source` formats

1. **Full module:** defines `def register_<snake>(` where `<snake>` is the snake_case folder name derived from `new_unit_type`. The file is written verbatim.
2. **Step body only:** any other non-empty source is indented into the body of `_step(params, inputs, state, dt)`; `register_<snake>()` is generated and wires a minimal `UnitSpec` with default `data` → `data` ports.

## Behaviour

1. Resolves `code_block_id` on `graph`, reads `source`, writes `README.md`, `__init__.py`, and `<snake>.py`.
2. Imports `units.<env>.<snake>.<snake>` and runs `register_<snake>()`.
3. Optionally patches `units/<env>/__init__.py` when that package uses the standard `register_env_loader` layout (see main canonical README for caveats).

## Outputs

- **`data`:** result dict on success (paths, flags, errors from scaffold).
- **`error`:** non-empty string on validation or scaffold failure.
