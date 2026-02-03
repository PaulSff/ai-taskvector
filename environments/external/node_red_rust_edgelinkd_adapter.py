"""
EdgeLinkd runtime adapter (stub).

EdgeLinkd is a Node-RED–compatible runtime reimplemented in Rust:
https://github.com/oldrev/edgelinkd

- Drop-in replacement: uses existing flows.json; same default UI port (1888).
- ~10x lower memory, native performance; function node uses QuickJS.
- Run: cargo run --release -- [FLOWS_PATH]; --headless for production.
- Ideal for edge devices and faster execution of Node-RED workflows.

Same roundtrip as Node-RED: (1) import full workflow, (2) train via this adapter
(EdgeLinkd runtime = env), (3) use trained model in the flow. See docs/DEPLOYMENT_NODERED.md.

This module: **EdgeLinkd runtime as external environment (training).**
- Connect to EdgeLinkd (HTTP API on default 127.0.0.1:1888 or configurable); wrap as gym.Env.
- Config: edgelinkd_url (default http://127.0.0.1:1888), flows_path (optional),
  observation_sources, action_targets, reward_config or goal.
- Implement by subclassing BaseExternalWrapper: _connect(), _get_obs(), _send_action(), _reward().

When implemented, this adapter can share connection logic with node_red_adapter (same flow
format and likely similar admin/API surface); this stub exists to document EdgeLinkd
as a first-class runtime option for faster execution.
"""
from typing import Any

import gymnasium as gym

from environments.external.base import BaseExternalWrapper


def load_edgelinkd_env(config: dict[str, Any]) -> gym.Env:
    """
    Load EdgeLinkd runtime as a Gymnasium env (stub).

    Config may include: edgelinkd_url (default http://127.0.0.1:1888),
    flows_path (optional), observation_sources (sensor node ids or topics),
    action_targets (valve/actuator node ids or topics), reward_config or goal.
    """
    raise NotImplementedError(
        "EdgeLinkd adapter not implemented. "
        "EdgeLinkd is a Node-RED–compatible Rust runtime for faster execution. "
        "Implement by subclassing BaseExternalWrapper (same pattern as node_red_adapter). "
        "See https://github.com/oldrev/edgelinkd and docs/DEPLOYMENT_NODERED.md."
    )


class EdgeLinkdEnvWrapper(BaseExternalWrapper):
    """
    Wrap EdgeLinkd runtime as gym.Env (stub).

    _connect(): connect to EdgeLinkd (HTTP API, default :1888); set obs/action spaces.
    _get_obs(): read observation from EdgeLinkd (sensor node outputs).
    _send_action(): send action to EdgeLinkd (inject into valve/actuator nodes).
    _reward(): compute from goal config or from a reward node.
    """

    def _connect(self) -> None:
        raise NotImplementedError(
            "EdgeLinkdEnvWrapper: connect to EdgeLinkd runtime; set observation_space, action_space."
        )

    def _get_obs(self):
        raise NotImplementedError("EdgeLinkdEnvWrapper: read observation from EdgeLinkd sensor outputs.")

    def _send_action(self, action) -> None:
        raise NotImplementedError("EdgeLinkdEnvWrapper: send action to EdgeLinkd valve/actuator nodes.")

    def _reward(self) -> float:
        raise NotImplementedError("EdgeLinkdEnvWrapper: compute reward from goal or node.")
