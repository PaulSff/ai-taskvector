"""
Runnable servers and bridge for inference and ComfyUI training.

- inference_server: unified POST /predict (RL + LLM); use --llm-only or --rl-only to restrict.
- rl_inference_server / llm_inference_server: thin entry points (delegate to inference_server).
- comfyui_bridge: POST /step that drives ComfyUI workflow for training.

Run:
  python -m server.inference_server --model path/to/model.zip
  python -m server.inference_server --llm-only --port 8000
  python -m server.comfyui_bridge --workflow workflow.json --port 8189
"""
