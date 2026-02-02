"""
Node-RED runtime adapter (stub).

Node-RED integration is **roundtrip**: (1) import full workflow, (2) train the full
process via this adapter (Node-RED runtime = env), (3) use the trained model in the
flow as a custom node. See docs/DEPLOYMENT_NODERED.md.

This module: **Node-RED runtime as external environment (training).**
- Connect to Node-RED runtime; wrap sensors/observations in, actions out as gym.Env.
- Config: Node-RED URL or MQTT broker, observation sources (sensor nodes), action
  targets (valve/actuator nodes), reward (goal config or Node-RED node).
- Implement by subclassing BaseExternalWrapper: _connect(), _get_obs(),
  _send_action(), _reward().

Deployment (model as Node-RED node) is separate: custom node that loads the trained
model; see docs/DEPLOYMENT_NODERED.md.
"""
from typing import Any

import gymnasium as gym

from environments.external.base import BaseExternalWrapper


def load_node_red_env(config: dict[str, Any]) -> gym.Env:
    """
    Load Node-RED runtime as a Gymnasium env (stub).

    Config may include: node_red_url (HTTP admin API or flow endpoint),
    mqtt_broker (optional), observation_sources (sensor node ids or topics),
    action_targets (valve/actuator node ids or topics), reward_config or goal.
    """
    raise NotImplementedError(
        "Node-RED adapter not implemented. "
        "Node-RED runtime can be used as the external env (sensors in, actions out); "
        "training would leverage its I/O. Implement by subclassing BaseExternalWrapper. "
        "See docs/DEPLOYMENT_NODERED.md and docs/ENVIRONMENTS_DESIGN.md."
    )


class NodeRedEnvWrapper(BaseExternalWrapper):
    """
    Wrap Node-RED runtime as gym.Env (stub).

    _connect(): connect to Node-RED (HTTP API, MQTT, or bridge); set obs/action spaces.
    _get_obs(): read current observation from Node-RED (sensor node outputs).
    _send_action(): send action to Node-RED (inject into valve/actuator nodes).
    _reward(): compute from goal config or from a Node-RED reward node.
    """

    def _connect(self) -> None:
        raise NotImplementedError(
            "NodeRedEnvWrapper: connect to Node-RED runtime (HTTP/MQTT); set observation_space, action_space."
        )

    def _get_obs(self):
        raise NotImplementedError("NodeRedEnvWrapper: read observation from Node-RED sensor outputs.")

    def _send_action(self, action) -> None:
        raise NotImplementedError("NodeRedEnvWrapper: send action to Node-RED valve/actuator nodes.")

    def _reward(self) -> float:
        raise NotImplementedError("NodeRedEnvWrapper: compute reward from goal or Node-RED.")
