"""
EdgeLinkd runtime adapter.

EdgeLinkd is a Node-RED–compatible runtime (https://github.com/oldrev/edgelinkd).
Uses the same **step-endpoint convention** as the Node-RED adapter: the flow must
expose POST step_url (default http://127.0.0.1:1888/step) with the same request/response
shape. So we reuse NodeRedEnvWrapper with a default URL for EdgeLinkd (port 1888).
"""
from typing import Any

import gymnasium as gym

from environments.external.node_red_adapter import NodeRedEnvWrapper


def load_edgelinkd_env(config: dict[str, Any]) -> gym.Env:
    """
    Load EdgeLinkd runtime as a Gymnasium env.

    Config: same as Node-RED adapter. step_url defaults to http://127.0.0.1:1888/step
    if only edgelinkd_url is given (EdgeLinkd default port is 1888).
    """
    cfg = dict(config)
    if "step_url" not in cfg and "edgelinkd_url" in cfg:
        cfg["step_url"] = cfg["edgelinkd_url"].rstrip("/") + "/step"
    elif "step_url" not in cfg:
        cfg["step_url"] = "http://127.0.0.1:1888/step"
    return NodeRedEnvWrapper(cfg)


class EdgeLinkdEnvWrapper(NodeRedEnvWrapper):
    """
    Wrap EdgeLinkd runtime as gym.Env. Same as NodeRedEnvWrapper (step-endpoint convention).
    Exists for clarity; load_edgelinkd_env() returns NodeRedEnvWrapper with EdgeLinkd default URL.
    """

    pass
