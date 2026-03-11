"""
Run console: helpers to execute the current graph and format outputs for the bottom console.
Used by the workflow tab Run button; console appears under the workflow (1/6 height) on click.
"""
from __future__ import annotations

import json
from typing import Any

from core.schemas.process_graph import ProcessGraph


def format_run_outputs(outputs: dict[str, Any]) -> str:
    """Format executor outputs as terminal log lines."""
    lines: list[str] = []
    for unit_id, port_values in sorted(outputs.items()):
        if not isinstance(port_values, dict):
            lines.append(f"[{unit_id}] (non-dict output)")
            continue
        for port_name, value in sorted(port_values.items()):
            if value is None:
                s = "None"
            elif isinstance(value, str):
                s = value[:500] + ("..." if len(value) > 500 else "")
            elif isinstance(value, (dict, list)):
                try:
                    s = json.dumps(value, ensure_ascii=False)[:500]
                    if len(json.dumps(value)) > 500:
                        s += "..."
                except (TypeError, ValueError):
                    s = repr(value)[:500]
            else:
                s = str(value)[:500]
            lines.append(f"  {unit_id}.{port_name}: {s}")
    return "\n".join(lines) if lines else "(no outputs)"


def build_initial_inputs_for_run(graph: ProcessGraph, user_message: str) -> dict[str, dict[str, Any]]:
    """Build initial_inputs for Inject units: each gets {'data': user_message}."""
    initial: dict[str, dict[str, Any]] = {}
    msg = (user_message or "").strip() or "(no message)"
    for u in graph.units:
        if u.type == "Inject":
            initial[u.id] = {"data": msg}
    return initial


def run_graph_sync(graph: ProcessGraph, initial_inputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Run graph once via executor; returns outputs. Call from thread."""
    from units.register_env_agnostic import register_env_agnostic_units

    register_env_agnostic_units()
    try:
        from units.data_bi import register_data_bi_units
        register_data_bi_units()
    except Exception:
        pass
    try:
        from units.web import register_web_units
        register_web_units()
    except Exception:
        pass

    from runtime.executor import GraphExecutor

    executor = GraphExecutor(graph)
    return executor.execute(initial_inputs=initial_inputs or {})
