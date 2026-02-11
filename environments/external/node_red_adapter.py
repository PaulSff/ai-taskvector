"""
Node-RED runtime adapter.

Node-RED integration is **roundtrip**: (1) import full workflow, (2) train the full
process via this adapter (Node-RED runtime = env), (3) use the trained model in the
flow as a custom node. See docs/DEPLOYMENT_NODERED.md.

**Step-endpoint convention:** The flow must expose an HTTP or WebSocket endpoint that
accepts JSON and returns observation, reward, and done.
- Step: { "action": [float, ...] } → { "observation": [...], "reward": float, "done": bool }
- Reset: { "reset": true } → { "observation": [...], "reward": 0, "done": false }

Transport: config["transport"] = "http" (default) or "websocket". For WebSocket use
ws_url (e.g. ws://127.0.0.1:1880/step); for HTTP use step_url.
"""
import json
from typing import Any

import gymnasium as gym
import numpy as np
import requests
from gymnasium import spaces

from environments.external.base import BaseExternalWrapper
from schemas.external_io_spec import ExternalIOSpec

try:
    import websocket
except ImportError:
    websocket = None  # type: ignore[assignment]


def load_node_red_env(config: dict[str, Any]) -> gym.Env:
    """
    Load Node-RED runtime as a Gymnasium env.

    Config:
      transport: "http" (default) or "websocket".
      step_url: URL for HTTP (e.g. http://127.0.0.1:1880/step). Used when transport=http.
      ws_url: WebSocket URL (e.g. ws://127.0.0.1:1880/step). Used when transport=websocket.
      obs_shape: (n,) or int; optional, inferred from first response if omitted.
      action_shape: (n,) or int; optional, inferred if omitted.
      timeout: request timeout in seconds (default 10).
    """
    return NodeRedEnvWrapper(config)


class NodeRedEnvWrapper(BaseExternalWrapper):
    """
    Wrap Node-RED runtime as gym.Env via HTTP or WebSocket step endpoint.

    Same message shape for both transports:
    - Send { "action": [float, ...] } or { "reset": true }
    - Receive { "observation": [...], "reward": float, "done": bool }
    """

    def __init__(self, config: dict[str, Any], render_mode: str | None = None):
        super().__init__(config, render_mode)
        self._transport = (config.get("transport") or "http").lower()
        if self._transport not in ("http", "websocket"):
            self._transport = "http"
        if self._transport == "websocket" and websocket is None:
            raise ImportError("WebSocket transport requires: pip install websocket-client")
        base = (config.get("node_red_url") or "").rstrip("/")
        self._step_url = config.get("step_url") or base + "/step"
        self._ws_url = config.get("ws_url") or (
            base.replace("http://", "ws://").replace("https://", "wss://") + "/step"
            if base else ""
        )
        if self._transport == "websocket" and not self._ws_url:
            self._ws_url = "ws://127.0.0.1:1880/step"
        self._timeout = int(config.get("timeout", 10))
        self._obs_shape = config.get("obs_shape")
        self._action_shape = config.get("action_shape")
        self._io_spec = ExternalIOSpec.from_adapter_config(config)
        self._last_obs: np.ndarray | None = None
        self._last_reward: float = 0.0
        self._last_done: bool = False
        self._ws: Any = None
        # Set observation/action space before VecEnv wraps this env (it reads spaces at wrap time)
        self._connect()
        self._connected = True

    def _connect(self) -> None:
        # Probe reset to get observation shape and set spaces
        resp = self._request({"reset": True})
        obs_raw = resp.get("observation")
        if not isinstance(obs_raw, list):
            raise ValueError("Node-RED / RLOracle response must include 'observation' as a list on reset.")
        obs = np.array(obs_raw, dtype=np.float32).reshape(-1)
        self._last_obs = obs
        self._last_reward = float(resp.get("reward", 0))
        self._last_done = bool(resp.get("done", False))
        obs_dim = int(obs.size if obs.ndim == 1 else obs.shape[0])
        act_dim = obs_dim  # default; can be overridden by config

        # Prefer explicit semantics spec when provided.
        if self._io_spec.obs_dim() > 0:
            if self._obs_shape is not None and int(self._obs_shape) != self._io_spec.obs_dim():
                raise ValueError(
                    f"obs_shape ({self._obs_shape}) does not match observation_spec length ({self._io_spec.obs_dim()})."
                )
            obs_dim = self._io_spec.obs_dim()
        if self._io_spec.action_dim() > 0:
            if self._action_shape is not None and int(self._action_shape) != self._io_spec.action_dim():
                raise ValueError(
                    f"action_shape ({self._action_shape}) does not match action_spec length ({self._io_spec.action_dim()})."
                )
            act_dim = self._io_spec.action_dim()

        if self._obs_shape is not None:
            obs_dim = self._obs_shape if isinstance(self._obs_shape, int) else int(np.prod(self._obs_shape))
        if self._action_shape is not None:
            act_dim = self._action_shape if isinstance(self._action_shape, int) else int(np.prod(self._action_shape))

        # Optional schema validation: RLOracle may return names to confirm the contract.
        obs_names = resp.get("observation_names")
        act_names = resp.get("action_names")
        if self._io_spec.obs_dim() > 0 and isinstance(obs_names, list):
            expected = [x.name for x in self._io_spec.observation_spec]
            got = [str(x) for x in obs_names]
            if got != expected:
                raise ValueError(f"RLOracle observation_names mismatch. Expected {expected}, got {got}.")
        if self._io_spec.action_dim() > 0 and isinstance(act_names, list):
            expected = [x.name for x in self._io_spec.action_spec]
            got = [str(x) for x in act_names]
            if got != expected:
                raise ValueError(f"RLOracle action_names mismatch. Expected {expected}, got {got}.")

        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32
        )
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(act_dim,), dtype=np.float32
        )

    def _request(self, body: dict[str, Any]) -> dict[str, Any]:
        """Send JSON body and return JSON response (HTTP or WebSocket)."""
        if self._transport == "websocket":
            return self._ws_send(body)
        return self._http_send(body)

    def _http_send(self, body: dict[str, Any]) -> dict[str, Any]:
        r = requests.post(self._step_url, json=body, timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    def _ws_send(self, body: dict[str, Any]) -> dict[str, Any]:
        if self._ws is None:
            self._ws = websocket.create_connection(self._ws_url, timeout=self._timeout)
        self._ws.send(json.dumps(body))
        raw = self._ws.recv()
        return json.loads(raw)

    def _get_obs(self) -> np.ndarray:
        if self._last_obs is not None:
            return self._last_obs
        obs = np.zeros(self.observation_space.shape, dtype=np.float32)
        return obs

    def _send_action(self, action: np.ndarray) -> None:
        # Action comes from the policy in normalized [-1, 1]. If action_spec provides min/max,
        # map to real actuator ranges before sending to the RLOracle.
        a = np.array(action, dtype=np.float32).reshape(-1)
        a = np.clip(a, -1.0, 1.0)
        out: list[float] = []
        if self._io_spec.action_dim() > 0:
            if int(a.size) != self._io_spec.action_dim():
                raise ValueError(f"Action dim mismatch: got {int(a.size)}, expected {self._io_spec.action_dim()}.")
            for i, spec in enumerate(self._io_spec.action_spec):
                v = float(a[i])
                if spec.min is not None and spec.max is not None:
                    v = float(spec.min) + (v + 1.0) * 0.5 * (float(spec.max) - float(spec.min))
                out.append(v)
        else:
            out = [float(x) for x in a.tolist()]

        body = {"action": out}
        resp = self._request(body)
        obs_raw = resp.get("observation")
        if not isinstance(obs_raw, list):
            raise ValueError("Node-RED / RLOracle response must include 'observation' as a list.")
        obs_vec = np.array(obs_raw, dtype=np.float32).reshape(-1)
        if int(obs_vec.size) != int(self.observation_space.shape[0]):
            raise ValueError(
                f"Observation dim mismatch: got {int(obs_vec.size)}, expected {int(self.observation_space.shape[0])}."
            )

        # Apply optional observation transforms
        if self._io_spec.obs_dim() > 0:
            transformed: list[float] = []
            for i, spec in enumerate(self._io_spec.observation_spec):
                v = float(obs_vec[i])
                v = v * float(spec.scale) + float(spec.offset)
                if spec.clip_min is not None:
                    v = max(float(spec.clip_min), v)
                if spec.clip_max is not None:
                    v = min(float(spec.clip_max), v)
                transformed.append(v)
            obs_vec = np.array(transformed, dtype=np.float32)

        self._last_obs = obs_vec
        self._last_reward = float(resp.get("reward", 0))
        self._last_done = bool(resp.get("done", False))

    def _reward(self) -> float:
        return self._last_reward

    def _done(self) -> tuple[bool, bool]:
        return self._last_done, False

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        if not self._connected:
            self._connect()
            self._connected = True
            return self._get_obs(), {}
        resp = self._request({"reset": True})
        obs_raw = resp.get("observation")
        if not isinstance(obs_raw, list):
            raise ValueError("Node-RED / RLOracle response must include 'observation' as a list on reset.")
        self._last_obs = np.array(obs_raw, dtype=np.float32).reshape(-1)
        self._last_reward = float(resp.get("reward", 0))
        self._last_done = False
        return self._last_obs, {}
