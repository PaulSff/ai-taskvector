"""
Load a Gymnasium env from the registry (gym.make).
Config: env_id (str), kwargs (optional dict for gym.make).
"""
from typing import Any

import gymnasium as gym


def load_gymnasium_env(config: dict[str, Any]) -> gym.Env:
    """
    Create a Gymnasium env via gym.make(env_id, **kwargs).

    Args:
        config: Must have "env_id" (str). May have "kwargs" (dict) for gym.make.

    Returns:
        gym.Env
    """
    env_id = config.get("env_id")
    if not env_id:
        raise ValueError("Gymnasium config must include 'env_id'")
    kwargs = dict(config.get("kwargs") or {})
    return gym.make(env_id, **kwargs)
