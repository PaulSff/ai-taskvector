"""
IDAES simulator adapter (stub).
Wraps an IDAES flowsheet as a Gymnasium env. Implement when IDAES integration is needed.
"""
from typing import Any

import gymnasium as gym


def load_idaes_env(config: dict[str, Any]) -> gym.Env:
    """
    Load an IDAES flowsheet and wrap as gym.Env (stub).

    Config may include: flowsheet_path, control_inputs, observation_vars, reward_config.
    """
    raise NotImplementedError(
        "IDAES adapter not implemented. "
        "See docs/ENVIRONMENTS_DESIGN.md §3. "
        "Implement when IDAES integration is needed."
    )
