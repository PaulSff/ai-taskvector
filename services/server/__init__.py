"""
Runnable servers and bridge for inference and ComfyUI training.
- workflow_server: workflow automations execution server
- inference_server: unified POST /predict (RL + LLM); use --llm-only or --rl-only to restrict.
- rl_inference_server / llm_inference_server: thin entry points (delegate to inference_server).
- comfyui_bridge: POST /step that drives ComfyUI workflow for training.

Run:
  python services/server/workflow_server.py
  python -m server.inference_server --model path/to/model.zip
  python -m server.inference_server --llm-only --port 8000
  python -m server.comfyui_bridge --workflow workflow.json --port 8189
"""

from .host_port_parser import _parse_host_port
from .round_robin import RoundRobinSlotAllocator

__all__ = [
    "RoundRobinSlotAllocator",
    "_parse_host_port",
]
