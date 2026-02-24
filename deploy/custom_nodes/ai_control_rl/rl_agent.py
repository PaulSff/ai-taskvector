"""
RLAgentPredict ComfyUI custom node: calls inference API, outputs action.
"""
import json
import urllib.request
from typing import Any


class RLAgentPredictNode:
    """
    Takes observations as input, calls inference API, outputs action.
    widgets_values: [inference_url, model_path]
    """

    CATEGORY = "AI Control RL"
    FUNCTION = "predict"
    RETURN_TYPES = ("FLOAT",)

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "obs_0": ("FLOAT", {"default": 0.0}),
                "inference_url": ("STRING", {"default": "http://127.0.0.1:8000/predict"}),
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

    def predict(
        self,
        obs_0: float = 0.0,
        obs_1: float = 0.0,
        obs_2: float = 0.0,
        obs_3: float = 0.0,
        obs_4: float = 0.0,
        obs_5: float = 0.0,
        obs_6: float = 0.0,
        obs_7: float = 0.0,
        inference_url: str = "http://127.0.0.1:8000/predict",
        **kwargs: Any,
    ) -> tuple[tuple[float, ...],]:
        observation = [
            float(obs_0), float(obs_1), float(obs_2), float(obs_3),
            float(obs_4), float(obs_5), float(obs_6), float(obs_7),
        ]
        url = inference_url or "http://127.0.0.1:8000/predict"
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps({"observation": observation}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            action = data.get("action", [0.0] * len(observation))
        except Exception:
            action = [0.0] * len(observation)
        return (tuple(float(x) for x in action),)
