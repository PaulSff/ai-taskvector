"""
Environments: single entry point for Gymnasium, External, and Custom envs.
All dynamics are external to our system; we send actions and receive feedback.
"""
from typing import Any

import gymnasium as gym

from environments.registry import EnvSource
from environments.gymnasium_loader import load_gymnasium_env
from environments.custom.thermodynamic import load_thermodynamic_env


def load_external_env(config: dict[str, Any]) -> gym.Env:
    """Load an external simulator via adapter (idaes, pcgym, etc.). Dispatches on config['adapter']."""
    adapter = config.get("adapter")
    if not adapter:
        raise ValueError("External config must include 'adapter' (e.g. 'idaes')")
    adapter_config = dict(config.get("config") or config)
    if adapter == "idaes":
        from environments.external.idaes_adapter import load_idaes_env
        return load_idaes_env(adapter_config)
    raise ValueError(f"Unknown external adapter: {adapter}")


def load_custom_env(config: dict[str, Any], **kwargs: Any) -> gym.Env:
    """Load a custom env (thermodynamic, etc.). Dispatches on config['type']."""
    env_type = config.get("type", "thermodynamic")
    if env_type == "thermodynamic":
        return load_thermodynamic_env(config, **kwargs)
    raise ValueError(f"Unknown custom env type: {env_type}")


def get_env(
    source: EnvSource,
    config: dict[str, Any],
    **kwargs: Any,
) -> gym.Env:
    """
    Single entry point: get a Gymnasium env from any source.

    Args:
        source: GYMNASIUM | EXTERNAL | CUSTOM.
        config: Source-specific config (env_id, adapter, process_graph_path, goal, etc.).
        **kwargs: Passed through to custom env (e.g. render_mode, randomize_params).

    Returns:
        gym.Env
    """
    if source == EnvSource.GYMNASIUM:
        return load_gymnasium_env(config)
    if source == EnvSource.EXTERNAL:
        return load_external_env(config)
    if source == EnvSource.CUSTOM:
        return load_custom_env(config, **kwargs)
    raise ValueError(f"Unknown source: {source}")


__all__ = [
    "EnvSource",
    "get_env",
    "load_gymnasium_env",
    "load_external_env",
    "load_custom_env",
]
