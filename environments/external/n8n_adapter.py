"""
n8n runtime adapter.

Uses the same HTTP step/reset contract as the Node-RED adapter. The n8n workflow
must expose a webhook that accepts POST and returns JSON (e.g. add RLOracle via add_pipeline and export to n8n).

**Step-endpoint convention (same as Node-RED):**
- Step: { "action": [float, ...] } → { "observation": [...], "reward": float, "done": bool }
- Reset: { "reset": true } → { "observation": [...], "reward": 0, "done": false }

Configure step_url to your n8n production webhook URL (workflow must be active).
"""
from typing import Any

import gymnasium as gym

from environments.external.node_red_adapter import NodeRedEnvWrapper


def load_n8n_env(config: dict[str, Any]) -> gym.Env:
    """
    Load n8n runtime as a Gymnasium env via HTTP step endpoint.

    Same contract as Node-RED: POST JSON to step_url, receive observation/reward/done.

    Config:
      step_url: Webhook URL (e.g. https://your-n8n.example.com/webhook/step).
                Must be the production webhook URL when the workflow is active.
      observation_spec: Optional list of { name, ... } for observation semantics.
      action_spec: Optional list of { name, min, max, ... } for action semantics.
      timeout: Request timeout in seconds (default 10).
    """
    cfg = dict(config)
    cfg.setdefault("transport", "http")  # n8n adapter is HTTP-only
    return NodeRedEnvWrapper(cfg)
