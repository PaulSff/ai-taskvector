"""
RL model inference server. Loads a trained SB3 model and exposes HTTP /predict.

Universal API: POST /predict with { "observation": [float, ...] } returns { "action": [float, ...] }.
Fits any trained model (PPO, SAC, etc.) from stable_baselines3.

Run:
  python -m deploy.rl_inference_server --model models/temperature_controller/best/best_model.zip
  python -m deploy.rl_inference_server --model path/to/model.zip --port 8001 --host 0.0.0.0
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


def _load_model(model_path: str):
    """Load SB3 model. Lazy import to avoid loading torch/sb3 if only --help."""
    from stable_baselines3 import PPO
    path = Path(model_path)
    if not path.exists():
        raise FileNotFoundError(f"Model not found: {path}")
    return PPO.load(str(path))


def create_app(model_path: str):
    """Create FastAPI app with /predict endpoint."""
    try:
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as e:
        raise ImportError("Install fastapi and uvicorn: pip install fastapi uvicorn") from e

    model = _load_model(model_path)
    app = FastAPI(title="RL Inference", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])

    @app.post("/predict")
    def predict(body: dict) -> dict:
        """Predict action from observation. body.observation = [float, ...]."""
        obs = body.get("observation")
        if obs is None:
            return {"error": "missing observation", "action": [0.0]}
        obs_arr = np.array(obs, dtype=np.float32)
        if obs_arr.ndim == 1:
            obs_arr = obs_arr.reshape(1, -1)
        action, _ = model.predict(obs_arr, deterministic=True)
        act_list = action.flatten().tolist()
        return {"action": act_list}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="RL model inference server")
    parser.add_argument("--model", "-m", required=True, help="Path to model .zip")
    parser.add_argument("--port", "-p", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    app = create_app(args.model)
    try:
        import uvicorn
        uvicorn.run(app, host=args.host, port=args.port)
    except ImportError:
        print("Install uvicorn: pip install uvicorn", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
