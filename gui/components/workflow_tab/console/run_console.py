"""
Helpers for the workflow run console: format executor output, align Debug log paths with settings,
and optional synchronous graph execution (GraphExecutor).

Used by :mod:`gui.components.workflow_tab.console.console` for the bottom panel; ``format_run_outputs`` /
``debug_log_param_overrides_for_graph_dict`` have no Flet dependency.
"""
from __future__ import annotations

import json
from typing import Any

from core.schemas.process_graph import ProcessGraph


def debug_log_param_overrides_for_graph_dict(
    graph_dict: Any, log_path: str
) -> dict[str, dict[str, Any]]:
    """Build ``unit_param_overrides`` for RunWorkflow so every **Debug** unit writes to ``log_path``.

    Without this, Debug falls back to ``log.txt`` while the console grep uses
    ``get_debug_log_path()`` from settings — paths diverge after the user changes the setting.
    """
    if not isinstance(graph_dict, dict):
        return {}
    units = graph_dict.get("units")
    if not isinstance(units, list):
        return {}
    lp = (log_path or "").strip()
    if not lp:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for u in units:
        if not isinstance(u, dict):
            continue
        if str(u.get("type") or "").strip() != "Debug":
            continue
        uid = u.get("id")
        if isinstance(uid, str) and uid.strip():
            out[uid.strip()] = {"log_path": lp}
    return out


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
    """Build initial_inputs for Inject units: each gets {'data': user_message} when non-empty.
    When empty, omit so Injects use params or Template connection."""
    initial: dict[str, dict[str, Any]] = {}
    msg = (user_message or "").strip()
    if not msg:
        return initial
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
