"""
Ryven runtime adapter (WebSocket + HTTP step-endpoint).

Ryven is a Python-native flow-based editor (https://github.com/leon-thomm/Ryven).
Same roundtrip as Node-RED: (1) import full workflow, (2) train full process via
this adapter (Ryven runtime = env), (3) use trained model as a node in the flow.
See docs/WORKFLOW_EDITORS_AND_CODE.md.

**Step-endpoint convention:** The Ryven flow (or a bridge that runs ryvencore and
exposes an endpoint) must expose HTTP or WebSocket with the same message shape as
Node-RED: send { "action": [...] } or { "reset": true }, receive
{ "observation": [...], "reward": float, "done": bool }. Default port 1899 to avoid
clashing with Node-RED (1880) and EdgeLinkd (1888).

Implement Ryven as WebSocket (or HTTP): reuse the Node-RED adapter logic with
Ryven-specific default URLs.
"""
from typing import Any

import gymnasium as gym

from environments.external.node_red_adapter import NodeRedEnvWrapper


def load_ryven_env(config: dict[str, Any]) -> gym.Env:
    """
    Load Ryven runtime as a Gymnasium env (WebSocket or HTTP step-endpoint).

    Uses the same step-endpoint convention as Node-RED. Config is passed through
    to NodeRedEnvWrapper with Ryven defaults when URLs are omitted.

    Config:
      transport: "http" (default) or "websocket".
      step_url: HTTP URL (default http://127.0.0.1:1899/step).
      ws_url: WebSocket URL (default ws://127.0.0.1:1899/step).
      obs_shape, action_shape, timeout: same as Node-RED adapter.
    """
    cfg = dict(config)
    base = (cfg.get("node_red_url") or cfg.get("ryven_url") or "http://127.0.0.1:1899").rstrip("/")
    if "step_url" not in cfg and "node_red_url" not in cfg and "ryven_url" not in cfg:
        cfg["step_url"] = base + "/step"
    if "ws_url" not in cfg:
        ws_base = base.replace("http://", "ws://").replace("https://", "wss://")
        cfg["ws_url"] = ws_base + "/step"
    return NodeRedEnvWrapper(cfg)
