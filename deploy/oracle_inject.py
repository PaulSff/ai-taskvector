"""
RLOracle code for canonical topology only.

Renders Oracle step/collector code as code_blocks for the canonical step_driver and step_rewards
units. Used by add_pipeline (type RLOracle). No separate Oracle units; deploy uses the same
canonical graph and export. See docs/DEPLOYMENT_NODERED.md and units/canonical/PIPELINES-WIRING.md.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from schemas.external_io_spec import ExternalIOSpec

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _load_template(name: str) -> str:
    """Load template source by name."""
    path = _TEMPLATES_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Oracle template not found: {path}")
    return path.read_text()


def _render_step_driver(
    observation_names: list[str],
    action_names: list[str],
    obs_context_prefix: str = "obs_",
    step_count_key: str = "step_count",
) -> str:
    """Render step driver template."""
    template = _load_template("rloracle_step_driver.js")
    return (
        template.replace("__TPL_OBS_NAMES__", json.dumps(observation_names))
        .replace("__TPL_ACT_NAMES__", json.dumps(action_names))
        .replace("__TPL_OBS_PREFIX__", json.dumps(obs_context_prefix))
        .replace("__TPL_STEP_KEY__", json.dumps(step_count_key))
    )


def _render_collector(
    observation_names: list[str],
    reward_config: dict[str, Any],
    max_steps: int = 600,
    obs_context_prefix: str = "obs_",
    step_count_key: str = "step_count",
) -> str:
    """Render collector template."""
    template = _load_template("rloracle_collector.js")
    return (
        template.replace("__TPL_OBS_NAMES__", json.dumps(observation_names))
        .replace("__TPL_REWARD__", json.dumps(reward_config or {}))
        .replace("__TPL_MAX_STEPS__", str(max_steps))
        .replace("__TPL_OBS_PREFIX__", json.dumps(obs_context_prefix))
        .replace("__TPL_STEP_KEY__", json.dumps(step_count_key))
    )


def _render_step_driver_n8n(
    observation_names: list[str],
    action_names: list[str],
    obs_context_prefix: str = "obs_",
    step_count_key: str = "step_count",
) -> str:
    """Render n8n step driver template (uses $getWorkflowStaticData)."""
    template = _load_template("rloracle_step_driver_n8n.js")
    return (
        template.replace("__TPL_OBS_NAMES__", json.dumps(observation_names))
        .replace("__TPL_ACT_NAMES__", json.dumps(action_names))
        .replace("__TPL_OBS_PREFIX__", json.dumps(obs_context_prefix))
        .replace("__TPL_STEP_KEY__", json.dumps(step_count_key))
    )


def _render_collector_n8n(
    observation_names: list[str],
    reward_config: dict[str, Any],
    max_steps: int = 600,
    obs_context_prefix: str = "obs_",
    step_count_key: str = "step_count",
) -> str:
    """Render n8n collector template (uses $getWorkflowStaticData)."""
    template = _load_template("rloracle_collector_n8n.js")
    return (
        template.replace("__TPL_OBS_NAMES__", json.dumps(observation_names))
        .replace("__TPL_REWARD__", json.dumps(reward_config or {}))
        .replace("__TPL_MAX_STEPS__", str(max_steps))
        .replace("__TPL_OBS_PREFIX__", json.dumps(obs_context_prefix))
        .replace("__TPL_STEP_KEY__", json.dumps(step_count_key))
    )


def _params_from_adapter_config(adapter_config: dict[str, Any]) -> tuple[list[str], list[str], dict, int]:
    """Extract observation_names, action_names, reward_config, max_steps from adapter_config."""
    io_spec = ExternalIOSpec.from_adapter_config(adapter_config)
    obs_names = [x.name for x in io_spec.observation_spec] if io_spec.obs_dim() > 0 else []
    act_names = [x.name for x in io_spec.action_spec] if io_spec.action_dim() > 0 else []
    reward_config = dict(adapter_config.get("reward_config") or {})
    max_steps = int(adapter_config.get("max_steps", 600))
    return obs_names, act_names, reward_config, max_steps


def _render_step_driver_py(
    action_names: list[str],
    action_key: str = "__rl_oracle_action__",
) -> str:
    """Render PyFlow step driver template (state/inputs)."""
    template = _load_template("rloracle_step_driver.py")
    return (
        template.replace("__TPL_ACT_NAMES__", repr(action_names))
        .replace("__TPL_ACTION_KEY__", repr(action_key))
    )


def _render_collector_py(
    observation_source_ids: list[str],
    reward_config: dict[str, Any],
    max_steps: int = 600,
    step_count_key: str = "step_count",
) -> str:
    """Render PyFlow collector template (state/inputs)."""
    template = _load_template("rloracle_collector.py")
    return (
        template.replace("__TPL_OBS_SOURCE_IDS__", repr(observation_source_ids))
        .replace("__TPL_REWARD__", repr(reward_config or {}))
        .replace("__TPL_MAX_STEPS__", str(max_steps))
        .replace("__TPL_STEP_KEY__", repr(step_count_key))
    )


# Canonical unit ids used when attaching Oracle code to the single canonical topology (no extra Oracle units).
CANONICAL_STEP_DRIVER_ID = "step_driver"
CANONICAL_STEP_REWARDS_ID = "step_rewards"


def render_oracle_code_blocks_for_canonical(
    adapter_config: dict[str, Any],
    *,
    language: str = "javascript",
    observation_source_ids: list[str] | None = None,
    n8n_mode: bool = False,
    step_driver_id: str = CANONICAL_STEP_DRIVER_ID,
    step_rewards_id: str = CANONICAL_STEP_REWARDS_ID,
) -> list[dict[str, Any]]:
    """
    Return code_blocks for the canonical step_driver and step_rewards units only.
    Does not add any units. Use this for RLOracle add_pipeline when keeping a single canonical topology.
    """
    obs_names, act_names, reward_config, max_steps = _params_from_adapter_config(adapter_config)
    if not obs_names:
        obs_names = [f"obs_{i}" for i in range(4)]
    if not act_names:
        act_names = [f"act_{i}" for i in range(3)]
    obs_source_ids = observation_source_ids or adapter_config.get("observation_sources") or adapter_config.get("observation_source_ids") or []

    if language == "python":
        step_driver_src = _render_step_driver_py(act_names)
        collector_src = _render_collector_py(obs_source_ids, reward_config, max_steps)
        lang = "python"
    elif n8n_mode:
        step_driver_src = _render_step_driver_n8n(obs_names, act_names)
        collector_src = _render_collector_n8n(obs_names, reward_config, max_steps)
        lang = "javascript"
    else:
        step_driver_src = _render_step_driver(obs_names, act_names)
        collector_src = _render_collector(obs_names, reward_config, max_steps)
        lang = "javascript"

    return [
        {"id": step_driver_id, "language": lang, "source": step_driver_src},
        {"id": step_rewards_id, "language": lang, "source": collector_src},
    ]


