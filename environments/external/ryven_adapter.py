"""
Ryven runtime adapter (stub).

Ryven is a Python-native flow-based editor (https://github.com/leon-thomm/Ryven).
Same roundtrip as Node-RED: (1) import full workflow, (2) train full process via
this adapter (Ryven runtime = env), (3) use trained model as a node in the flow.
See docs/WORKFLOW_EDITORS_AND_CODE.md.

This module: **Ryven runtime as external environment (training).**
- Connect to Ryven/ryvencore runtime; wrap sensors in, actions out as gym.Env.
- Config: project/flow path or ryvencore session, observation data sources, action targets, reward (goal or node).
- Implement by subclassing BaseExternalWrapper: _connect(), _get_obs(), _send_action(), _reward().
"""
from typing import Any

import gymnasium as gym

from environments.external.base import BaseExternalWrapper


def load_ryven_env(config: dict[str, Any]) -> gym.Env:
    """
    Load Ryven/ryvencore runtime as a Gymnasium env (stub).

    Config may include: project_path or session, observation_sources (node/output ids),
    action_targets (node/input ids), reward_config or goal.
    """
    raise NotImplementedError(
        "Ryven adapter not implemented. "
        "Ryven runtime can be used as the external env (sensors in, actions out). "
        "Implement by subclassing BaseExternalWrapper. "
        "See docs/WORKFLOW_EDITORS_AND_CODE.md and docs/ENVIRONMENTS_DESIGN.md."
    )


class RyvenEnvWrapper(BaseExternalWrapper):
    """
    Wrap Ryven/ryvencore runtime as gym.Env (stub).

    _connect(): connect to Ryven/ryvencore; load flow; set obs/action spaces.
    _get_obs(): read observation from Ryven (data outputs).
    _send_action(): send action to Ryven (inject into data inputs / control nodes).
    _reward(): compute from goal config or from a Ryven reward node.
    """

    def _connect(self) -> None:
        raise NotImplementedError(
            "RyvenEnvWrapper: connect to Ryven/ryvencore; set observation_space, action_space."
        )

    def _get_obs(self):
        raise NotImplementedError("RyvenEnvWrapper: read observation from Ryven outputs.")

    def _send_action(self, action) -> None:
        raise NotImplementedError("RyvenEnvWrapper: send action to Ryven inputs/control nodes.")

    def _reward(self) -> float:
        raise NotImplementedError("RyvenEnvWrapper: compute reward from goal or Ryven node.")
