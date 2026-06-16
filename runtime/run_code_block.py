import asyncio
from typing import Any


def _run_code_block(
    source: str,
    node_id: str,
    state: dict[str, Any],
    inputs: dict[str, Any],
    params: dict[str, Any],
) -> Any:
    """Run a unit's code_block with state/inputs/params; return single value (PyFlow-adapter contract)."""
    # Normalize inputs: replace None with 0.0 without mutating caller dict
    inputs = {k: (0.0 if v is None else v) for k, v in (inputs or {}).items()}
    scope: dict[str, Any] = {
        "state": state,
        "inputs": inputs,
        "node_id": node_id,
        "params": params or {},
    }
    indented = "\n  ".join(source.strip().splitlines())
    wrapped = f"def _fn(state, inputs):\n  {indented}\n_result = _fn(state, inputs)"
    # Intentionally using scope as globals so node_id/params accessible; keep builtins available
    exec(wrapped, scope)
    return scope.get("_result", 0.0)


async def _run_code_block_async(
    source: str,
    node_id: str,
    state: dict[str, Any],
    inputs: dict[str, Any],
    params: dict[str, Any],
) -> Any:
    """Async wrapper that executes the existing sync _run_code_block in a thread."""
    return await asyncio.to_thread(
        _run_code_block, source, node_id, state, inputs, params
    )
