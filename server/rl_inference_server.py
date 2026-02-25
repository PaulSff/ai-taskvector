"""
RL model inference server. Thin entry point for the unified inference server.

Runs the unified server with --rl-only (requires --model).
Universal API: POST /predict with { "observation": [float, ...] } returns { "action": [float, ...] }.

Run:
  python -m server.rl_inference_server --model models/temperature_controller/best/best_model.zip
  python -m server.rl_inference_server --model path/to/model.zip --port 8000 --host 0.0.0.0

Or use the unified server: python -m server.inference_server --model path/to/model.zip --rl-only
"""
from __future__ import annotations

import sys

# Delegate to unified server with --rl-only (--model required by unified server)
if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--rl-only"] + [a for a in sys.argv[1:] if a != "--rl-only"]
    from server.inference_server import main
    main()
