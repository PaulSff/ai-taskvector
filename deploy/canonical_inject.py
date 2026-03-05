"""
Inject code_blocks for canonical units (step_driver, join, switch, split, step_rewards)
so the full setup exports as runnable nodes to Node-RED, n8n, and PyFlow.

When a graph has canonical units (by role) but no code_block, we render from templates
so export produces a complete, runnable flow. Aligned for our runtime and external runtimes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from schemas.process_graph import ProcessGraph
from units.registry import get_unit_spec

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _load_template(name: str) -> str:
    path = _TEMPLATES_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Canonical template not found: {path}")
    return path.read_text()


def _render_step_driver_js(unit_id: str) -> str:
    t = _load_template("canonical_step_driver.js")
    return t.replace("__TPL_UNIT_ID__", repr(unit_id))


def _render_join_js(unit_id: str, num_inputs: int) -> str:
    t = _load_template("canonical_join.js")
    return t.replace("__TPL_NUM_INPUTS__", str(num_inputs)).replace("__TPL_UNIT_ID__", repr(unit_id))


def _render_switch_js(unit_id: str, num_outputs: int) -> str:
    t = _load_template("canonical_switch.js")
    return t.replace("__TPL_NUM_OUTPUTS__", str(num_outputs)).replace("__TPL_UNIT_ID__", repr(unit_id))


def _render_split_js(unit_id: str, num_outputs: int) -> str:
    t = _load_template("canonical_split.js")
    return t.replace("__TPL_NUM_OUTPUTS__", str(num_outputs)).replace("__TPL_UNIT_ID__", repr(unit_id))


def _render_step_driver_py() -> str:
    return _load_template("canonical_step_driver.py")


def _render_join_py(num_inputs: int) -> str:
    t = _load_template("canonical_join.py")
    return t.replace("__TPL_NUM_INPUTS__", str(num_inputs))


def _render_switch_py(num_outputs: int) -> str:
    t = _load_template("canonical_switch.py")
    return t.replace("__TPL_NUM_OUTPUTS__", str(num_outputs))


def _render_split_py(num_outputs: int) -> str:
    t = _load_template("canonical_split.py")
    return t.replace("__TPL_NUM_OUTPUTS__", str(num_outputs))


def _render_step_rewards_py(max_steps: int, reward: Any, step_key: str = "step_count") -> str:
    t = _load_template("canonical_step_rewards.py")
    return (
        t.replace("__TPL_MAX_STEPS__", str(max_steps))
        .replace("__TPL_REWARD__", repr(reward))
        .replace("__TPL_STEP_KEY__", repr(step_key))
    )


def _render_step_rewards_js(unit_id: str, max_steps: int, reward: Any, step_key: str = "step_count") -> str:
    t = _load_template("canonical_step_rewards.js")
    reward_js = json.dumps(reward) if reward is not None else "null"
    return (
        t.replace("__TPL_UNIT_ID__", json.dumps(unit_id))
        .replace("__TPL_MAX_STEPS__", str(max_steps))
        .replace("__TPL_REWARD__", reward_js)
        .replace("__TPL_STEP_KEY__", json.dumps(step_key))
    )


def get_canonical_code_for_unit(unit: Any, language: str) -> str | None:
    """
    Return rendered template source for a canonical unit, or None if unit is not canonical or params missing.
    language: "javascript" (Node-RED/n8n) or "python" (PyFlow).
    """
    spec = get_unit_spec(unit.type) if getattr(unit, "type", None) else None
    if spec is None or not spec.role:
        return None
    params = dict(getattr(unit, "params", None) or {})
    unit_id = getattr(unit, "id", "") or ""

    if language == "python":
        if spec.role == "step_driver":
            return _render_step_driver_py()
        if spec.role == "join":
            n = int(params.get("num_inputs", 8))
            return _render_join_py(min(max(n, 1), 8))
        if spec.role == "switch":
            n = int(params.get("num_outputs", 8))
            return _render_switch_py(min(max(n, 1), 8))
        if spec.role == "split":
            n = int(params.get("num_outputs", 8))
            return _render_split_py(min(max(n, 1), 8))
        if spec.role == "step_rewards":
            max_steps = int(params.get("max_steps", 600))
            reward = params.get("reward")
            return _render_step_rewards_py(max_steps, reward)
        return None

    if language == "javascript":
        if spec.role == "step_driver":
            return _render_step_driver_js(unit_id)
        if spec.role == "join":
            n = int(params.get("num_inputs", 8))
            return _render_join_js(unit_id, min(max(n, 1), 8))
        if spec.role == "switch":
            n = int(params.get("num_outputs", 8))
            return _render_switch_js(unit_id, min(max(n, 1), 8))
        if spec.role == "split":
            n = int(params.get("num_outputs", 8))
            return _render_split_js(unit_id, min(max(n, 1), 8))
        if spec.role == "step_rewards":
            max_steps = int(params.get("max_steps", 600))
            reward = params.get("reward")
            return _render_step_rewards_js(unit_id, max_steps, reward)
        return None

    return None


def enrich_code_map_for_export(
    graph: ProcessGraph,
    code_map: dict[str, str],
    export_format: str,
) -> dict[str, str]:
    """
    Add code for any canonical unit that has no code_block so export produces runnable nodes.
    export_format: "node_red" | "n8n" -> javascript; "pyflow" -> python.
    Returns a new dict (does not mutate code_map).
    """
    try:
        from units.register_env_agnostic import register_env_agnostic_units
        register_env_agnostic_units()
    except Exception:
        pass
    lang = "python" if export_format == "pyflow" else "javascript"
    existing = set(code_map)
    out = dict(code_map)
    for u in graph.units:
        if u.id in existing:
            continue
        src = get_canonical_code_for_unit(u, lang)
        if src:
            out[u.id] = src
    return out
