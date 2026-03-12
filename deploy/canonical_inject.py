"""
Inject code_blocks for canonical units (step_driver, join, merge, prompt, switch, split, step_rewards)
so the full setup exports as runnable nodes to Node-RED, n8n, and PyFlow.

When a graph has canonical units (by role or type) but no code_block, we render from templates
so export produces a complete, runnable flow. Prompt: template (from params or template_path) + data -> system_prompt.
Aligned for our runtime and external runtimes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.schemas.process_graph import ProcessGraph
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


def _render_merge_py(num_inputs: int) -> str:
    t = _load_template("canonical_merge.py")
    return t.replace("__TPL_NUM_INPUTS__", str(num_inputs))


def _render_merge_js(unit_id: str, num_inputs: int, keys: list[str] | None) -> str:
    t = _load_template("canonical_merge.js")
    if not keys or len(keys) < num_inputs:
        keys = [f"in_{i}" for i in range(num_inputs)]
    keys_json = json.dumps(keys[:num_inputs])
    return (
        t.replace("__TPL_NUM_INPUTS__", str(num_inputs))
        .replace("__TPL_UNIT_ID__", repr(unit_id))
        .replace("__TPL_KEYS_JSON__", keys_json)
    )


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


def _resolve_prompt_template_and_format_keys(unit: Any) -> tuple[str, list[str]]:
    """Resolve template string and format_keys from Prompt unit params (template_path relative to project root)."""
    params = dict(getattr(unit, "params", None) or {})
    base = Path(__file__).resolve().parent.parent
    if params.get("template_path"):
        p = Path(params["template_path"])
        if not p.is_absolute():
            params = {**params, "template_path": str(base / p)}
    try:
        from units.canonical.prompt.prompt import _load_template as prompt_load_template
        template_str, format_keys = prompt_load_template(params)
    except Exception:
        template_str = (params.get("template") or "").strip()
        format_keys = list(params.get("format_keys") or [])
        if isinstance(format_keys, (list, tuple)):
            format_keys = [str(k) for k in format_keys]
        else:
            format_keys = []
    return template_str or "", format_keys


def _render_prompt_py(template_str: str, format_keys: list[str]) -> str:
    t = _load_template("canonical_prompt.py")
    return (
        t.replace("__TPL_TEMPLATE__", repr(template_str))
        .replace("__TPL_FORMAT_KEYS_JSON__", str(format_keys))
    )


def _render_prompt_js(unit_id: str, template_str: str, format_keys: list[str]) -> str:
    t = _load_template("canonical_prompt.js")
    return (
        t.replace("__TPL_TEMPLATE__", json.dumps(template_str))
        .replace("__TPL_FORMAT_KEYS_JSON__", json.dumps(format_keys))
        .replace("__TPL_UNIT_ID__", json.dumps(unit_id))
    )


def get_canonical_code_for_unit(unit: Any, language: str) -> str | None:
    """
    Return rendered template source for a canonical unit, or None if unit is not canonical or params missing.
    language: "javascript" (Node-RED/n8n) or "python" (PyFlow).
    """
    unit_type = getattr(unit, "type", None)
    params = dict(getattr(unit, "params", None) or {})
    unit_id = getattr(unit, "id", "") or ""

    # Aggregate (no role): type-based dispatch
    if unit_type == "Aggregate":
        n = int(params.get("num_inputs", 8))
        n = min(max(n, 1), 8)
        if language == "python":
            return _render_merge_py(n)
        if language == "javascript":
            keys = params.get("keys")
            if isinstance(keys, (list, tuple)):
                keys = [str(k) for k in keys]
            else:
                keys = None
            return _render_merge_js(unit_id, n, keys)
        return None

    # Prompt (no role): template + data -> system_prompt; inject and deploy to external runtimes
    if unit_type == "Prompt":
        template_str, format_keys = _resolve_prompt_template_and_format_keys(unit)
        if not template_str:
            return None
        if language == "python":
            return _render_prompt_py(template_str, format_keys)
        if language == "javascript":
            return _render_prompt_js(unit_id, template_str, format_keys)
        return None

    spec = get_unit_spec(unit_type) if unit_type else None
    if spec is None or not spec.role:
        return None

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
