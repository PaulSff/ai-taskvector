"""
Unified inference server for RLAgent and LLMAgent. Single process, one POST /predict.

- RL path: body has observation (optional model_path to select model); uses loaded SB3 model.
- LLM path: body has observation + system_prompt, model_name, etc.; calls LLM_integrations.client.chat.

Use --llm-only or --rl-only to disable one path. Default: both enabled (RL if --model given).
Run:
  python -m server.inference_server --model path/to/model.zip
  python -m server.inference_server --llm-only --port 8000
  python -m server.inference_server --model path/to/model.zip --port 8000
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np

_DEFAULT_PORT = 8000
_DEFAULT_HOST = "127.0.0.1"


def _load_rl_model(model_path: str):
    """Load SB3 model. Lazy import to avoid loading torch/sb3 if only LLM used."""
    from stable_baselines3 import PPO
    path = Path(model_path)
    if not path.exists():
        raise FileNotFoundError(f"Model not found: {path}")
    return PPO.load(str(path))


def _parse_action_from_llm_response(text: str) -> list[float]:
    """Extract action vector from LLM response."""
    text = (text or "").strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
        if m:
            text = m.group(1)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "action" in parsed:
            arr = parsed["action"]
        elif isinstance(parsed, list):
            arr = parsed
        else:
            arr = [0.0]
        return [float(x) for x in arr][:16]
    except (json.JSONDecodeError, TypeError):
        pass
    for pattern in (r'"action"\s*:\s*\[[^\]]*\]', r'\[[\s\d.,\-]+\]'):
        m = re.search(pattern, text)
        if m:
            try:
                snippet = m.group(0)
                if snippet.startswith('"'):
                    snippet = "{" + snippet + "}"
                    arr = json.loads(snippet)["action"]
                else:
                    arr = json.loads(snippet)
                return [float(x) for x in arr][:16]
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
    nums = re.findall(r"-?\d+\.?\d*", text)
    if nums:
        return [float(x) for x in nums[:16]]
    return [0.0]


def _predict_rl(body: dict, model: Any) -> dict[str, Any]:
    """RL path: observation -> loaded model -> action."""
    obs = body.get("observation")
    if obs is None:
        return {"error": "missing observation", "action": [0.0]}
    obs_arr = np.array(obs, dtype=np.float32)
    if obs_arr.ndim == 1:
        obs_arr = obs_arr.reshape(1, -1)
    action, _ = model.predict(obs_arr, deterministic=True)
    return {"action": action.flatten().tolist()}


def _predict_llm(body: dict[str, Any]) -> dict[str, Any]:
    """LLM path: observation + prompt params -> LLM -> parse -> action."""
    observation = body.get("observation")
    if observation is None:
        return {"error": "missing observation", "action": [0.0]}
    if not isinstance(observation, list):
        observation = [float(observation)] if isinstance(observation, (int, float)) else [0.0]
    observation = [float(x) for x in observation]

    system_prompt = (body.get("system_prompt") or "").strip() or "You are a control agent. Output a JSON object with an 'action' key containing a list of numbers."
    user_prompt_template = (body.get("user_prompt_template") or "Observations: {observation_json}. Output only a JSON object with key 'action' and value a list of numbers.").strip()
    model_name = (body.get("model_name") or "llama3.2").strip()
    provider = (body.get("provider") or "ollama").strip()
    host = body.get("host") or "http://127.0.0.1:11434"

    user_content = user_prompt_template.replace("{observation_json}", json.dumps(observation))
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    try:
        from LLM_integrations import client as llm_client
    except ImportError:
        return {"error": "LLM_integrations not available", "action": [0.0] * max(1, len(observation))}

    config = {"model": model_name, "host": host} if provider == "ollama" else {"model": model_name}
    try:
        response_text = llm_client.chat(
            provider=provider,
            config=config,
            messages=messages,
            timeout_s=120,
        )
    except Exception as e:
        return {"error": str(e)[:200], "action": [0.0] * max(1, len(observation))}

    action = _parse_action_from_llm_response(response_text)
    if not action:
        action = [0.0] * max(1, len(observation))
    return {"action": action}


def create_app(
    *,
    rl_model_path: str | None = None,
    llm_only: bool = False,
    rl_only: bool = False,
) -> Any:
    """Create FastAPI app with single /predict that routes to RL or LLM."""
    try:
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as e:
        raise ImportError("Install fastapi and uvicorn: pip install fastapi uvicorn") from e

    rl_model = None
    if not llm_only and rl_model_path:
        rl_model = _load_rl_model(rl_model_path)

    app = FastAPI(title="Inference (RL + LLM)", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])

    @app.post("/predict")
    def predict(body: dict[str, Any]) -> dict[str, Any]:
        """Single endpoint: RL if no LLM params in body and model loaded; else LLM."""
        # Prefer LLM path if request looks like LLM (has system_prompt or model_name for LLM)
        is_llm_request = "system_prompt" in body or ("model_name" in body and "observation" in body)
        if is_llm_request and not rl_only:
            return _predict_llm(body)
        if rl_model is not None and not llm_only:
            return _predict_rl(body, rl_model)
        if llm_only:
            return _predict_llm(body)
        if rl_only:
            return {"error": "RL path requires --model to be set", "action": [0.0]}
        return {"error": "No RL model loaded (use --model) and request has no LLM params (system_prompt/model_name)", "action": [0.0]}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified inference server for RLAgent and LLMAgent (POST /predict)."
    )
    parser.add_argument("--model", "-m", default=None, help="Path to RL model .zip (required for RL path)")
    parser.add_argument("--llm-only", action="store_true", help="Disable RL path; only serve LLM inference")
    parser.add_argument("--rl-only", action="store_true", help="Disable LLM path; only serve RL inference (requires --model)")
    parser.add_argument("--port", "-p", type=int, default=_DEFAULT_PORT)
    parser.add_argument("--host", default=_DEFAULT_HOST)
    args = parser.parse_args()

    if args.rl_only and not args.model:
        print("Error: --rl-only requires --model", file=sys.stderr)
        sys.exit(1)
    if args.llm_only and args.rl_only:
        print("Error: use only one of --llm-only and --rl-only", file=sys.stderr)
        sys.exit(1)

    app = create_app(
        rl_model_path=args.model,
        llm_only=args.llm_only,
        rl_only=args.rl_only,
    )
    try:
        import uvicorn
        uvicorn.run(app, host=args.host, port=args.port)
    except ImportError:
        print("Install uvicorn: pip install uvicorn", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
