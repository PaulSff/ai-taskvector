# list_environment

Creates a new environment package under `units/<new_environment_id>/` and registers it with `register_env_loader`.

## Params

| Field | Required | Description |
|--------|----------|-------------|
| `action` | no | May be `list_environment`. |
| `new_environment_id` | yes | Tag for the new env (normalized to lowercase `[a-z0-9_]`). Must not already exist in `known_environment_tags()`. |
| `readme_md` | no | Written to `units/<tag>/README.md`. |

## Behaviour

1. Writes `units/<tag>/README.md` and `__init__.py` with `register_<tag>_units` + `register_env_loader`.
2. Appends a `try: import units.<tag>` block to `units/env_loaders.py` (after the semantics block).
3. Imports `units.<tag>` so the loader is active in the current process.

On failure after files were created, the new directory is removed. If `env_loaders.py` was already patched, the import is wrapped in `try/except` so startup stays safe.
