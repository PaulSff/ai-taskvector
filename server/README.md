# Server: runnable inference and bridge

This folder contains the **runnable servers and bridge** (single process). Deployment **injection** (templates, flow_inject, oracle_inject) stays in **deploy/**.

| Module | Purpose |
|--------|---------|
| **inference_server** | Unified POST /predict for RLAgent and LLMAgent. Use `--llm-only` or `--rl-only` to restrict. |
| **rl_inference_server** | Thin entry point: `--rl-only` + requires `--model`. |
| **llm_inference_server** | Thin entry point: `--llm-only`, default port 8001. |
| **comfyui_bridge** | POST /step that drives ComfyUI workflow for training. |

**Run only what you need** (from repo root). Pick one of the following:

- **RL inference only** (graphs with RLAgent):
  ```bash
  python -m server.rl_inference_server --model path/to/model.zip
  ```
- **LLM inference only** (graphs with LLMAgent):
  ```bash
  python -m server.llm_inference_server --port 8001
  ```
- **Both RL and LLM** (one server, same port):
  ```bash
  python -m server.inference_server --model path/to/model.zip --port 8000
  ```
- **ComfyUI training bridge** (drives ComfyUI for RL training):
  ```bash
  python -m server.comfyui_bridge --workflow workflow.json --port 8189 --comfy-url http://127.0.0.1:8188
  ```

See **deploy/README.md** for API and usage.
