"""
PyFlow runtime adapter (stub).

PyFlow is a Python-native node editor (https://github.com/pedroCabrera/PyFlow).
Same roundtrip as Node-RED: (1) import full workflow, (2) train full process via
this adapter (PyFlow runtime = env), (3) use trained model as a node in the flow.
See docs/WORKFLOW_EDITORS_AND_CODE.md.

This module: **PyFlow runtime as external environment (training).**
- Connect to PyFlow runtime (or run flow via PyFlow API); wrap sensors in, actions out as gym.Env.
- Config: flow path or in-memory graph, observation pins/sources, action pins/targets, reward (goal or node).
- Implement by subclassing BaseExternalWrapper: _connect(), _get_obs(), _send_action(), _reward().
"""
from typing import Any

import gymnasium as gym

from environments.external.base import BaseExternalWrapper


def load_pyflow_env(config: dict[str, Any]) -> gym.Env:
    """
    Load PyFlow runtime as a Gymnasium env (stub).

    Config may include: flow_path or graph, observation_sources (pin/node ids),
    action_targets (pin/node ids), reward_config or goal.
    """
    raise NotImplementedError(
        "PyFlow adapter not implemented. "
        "PyFlow runtime can be used as the external env (sensors in, actions out). "
        "Implement by subclassing BaseExternalWrapper. "
        "See docs/WORKFLOW_EDITORS_AND_CODE.md and docs/ENVIRONMENTS_DESIGN.md."
    )


class PyFlowEnvWrapper(BaseExternalWrapper):
    """
    Wrap PyFlow runtime as gym.Env (stub).

    _connect(): connect to PyFlow runtime / load flow; set obs/action spaces.
    _get_obs(): read observation from PyFlow (sensor/output pins).
    _send_action(): send action to PyFlow (inject into input pins / control nodes).
    _reward(): compute from goal config or from a PyFlow reward node.
    """

    def _connect(self) -> None:
        raise NotImplementedError(
            "PyFlowEnvWrapper: connect to PyFlow runtime; set observation_space, action_space."
        )

    def _get_obs(self):
        raise NotImplementedError("PyFlowEnvWrapper: read observation from PyFlow outputs.")

    def _send_action(self, action) -> None:
        raise NotImplementedError("PyFlowEnvWrapper: send action to PyFlow inputs/control nodes.")

    def _reward(self) -> float:
        raise NotImplementedError("PyFlowEnvWrapper: compute reward from goal or PyFlow node.")
