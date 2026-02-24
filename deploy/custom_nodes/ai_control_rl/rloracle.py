"""
RLOracle ComfyUI custom nodes: StepDriver (outputs action) and Collector (observations → reward).
"""
import json
import os
from typing import Any

# Default paths for bridge ↔ nodes communication (override via env)
_ACTION_FILE = os.environ.get("COMFYUI_RL_ACTION_FILE", "/tmp/comfyui_rl_action.json")
_RESULT_FILE = os.environ.get("COMFYUI_RL_RESULT_FILE", "/tmp/comfyui_rl_result.json")


class RLOracleStepDriverNode:
    """Outputs the current RL action (set by bridge before workflow execution)."""

    CATEGORY = "AI Control RL"
    FUNCTION = "get_action"
    RETURN_TYPES = ("FLOAT",)

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {"required": {}, "hidden": {"prompt": "PROMPT", "unique_id": "UNIQUE_ID"}}

    def get_action(self, **kwargs: Any) -> tuple[tuple[float, ...],]:
        try:
            with open(_ACTION_FILE) as f:
                data = json.load(f)
            action = data.get("action", [0.0])
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            action = [0.0]
        return (tuple(float(x) for x in action),)


class RLOracleCollectorNode:
    """
    Collects observation values from inputs, computes reward, writes result for bridge.
    reward_config: JSON string, e.g. {"type":"setpoint","target":0.5,"observation_index":0}
    max_steps: int
    """

    CATEGORY = "AI Control RL"
    FUNCTION = "collect"
    RETURN_TYPES = ()

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "obs_0": ("FLOAT", {"default": 0.0}),
                "reward_config": ("STRING", {"default": "{}"}),
                "max_steps": ("INT", {"default": 600, "min": 1, "max": 10000}),
            },
            "optional": {
                "obs_1": ("FLOAT", {"default": 0.0}),
                "obs_2": ("FLOAT", {"default": 0.0}),
                "obs_3": ("FLOAT", {"default": 0.0}),
                "obs_4": ("FLOAT", {"default": 0.0}),
                "obs_5": ("FLOAT", {"default": 0.0}),
                "obs_6": ("FLOAT", {"default": 0.0}),
                "obs_7": ("FLOAT", {"default": 0.0}),
            },
        }

    def collect(
        self,
        obs_0: float = 0.0,
        obs_1: float = 0.0,
        obs_2: float = 0.0,
        obs_3: float = 0.0,
        obs_4: float = 0.0,
        obs_5: float = 0.0,
        obs_6: float = 0.0,
        obs_7: float = 0.0,
        reward_config: str = "{}",
        max_steps: int = 600,
        **kwargs: Any,
    ) -> tuple[()]:
        observation = [
            float(obs_0), float(obs_1), float(obs_2), float(obs_3),
            float(obs_4), float(obs_5), float(obs_6), float(obs_7),
        ]
        reward = 0.0
        step_count = 1
        try:
            cfg = json.loads(reward_config) if reward_config else {}
            rtype = cfg.get("type", "setpoint")
            if rtype == "setpoint":
                idx = int(cfg.get("observation_index", 0))
                target = float(cfg.get("target", cfg.get("target_temp", 0)))
                reward = -abs((observation[idx] if idx < len(observation) else 0) - target)
            elif isinstance(cfg.get("reward"), (int, float)):
                reward = float(cfg["reward"])
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        done = step_count >= max_steps
        try:
            with open(_RESULT_FILE, "w") as f:
                json.dump({"observation": observation, "reward": reward, "done": done}, f)
        except OSError:
            pass
        return ()
