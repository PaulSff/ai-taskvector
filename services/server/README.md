# Server: runnable workflows, inference and bridge

This folder contains the **runnable servers and bridge** (single process). Deployment **injection** (templates, flow_inject, oracle_inject) stays in **deploy/**.

| Module | Purpose |
|--------|---------|
| **workflow_server** | Workflow execution server |
| **inference_server** | Unified POST /predict for RLAgent and LLMAgent. Use `--llm-only` or `--rl-only` to restrict. |
| **rl_inference_server** | Thin entry point: `--rl-only` + requires `--model`. |
| **llm_inference_server** | Thin entry point: `--llm-only`, default port 8001. |
| **comfyui_bridge** | POST /step that drives ComfyUI workflow for training. |

**Run only what you need** (from repo root). Pick one of the following:

- **Workflow server** (workflows execution)
  ```bash
  python services/server/workflow_server.py
  ```
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

---

# Workflow server

Async worker pool that consumes ZMQ “job” messages and executes each requested workflow in a separate spawned subprocess.

## Overview

For each incoming job:

1. Validate payload fields (`run_id`, `workflow_path` or `workflow_graph`, `inputs/overrides`, `response_endpoint`, `execution timeout`).
2. Spawn a subprocess that runs `run_workflow(...)` with the provided `run_id`.
   - If `response_endpoint` is provided, `run_workflow` publishes streamed tokens plus the final result or error to ZMQ itself.
3. The asyncio handler waits for the subprocess to finish (via an inter-process `multiprocessing.Queue`) to log success/failure.
4. Concurrency is limited with an asyncio semaphore (`max_concurrency`); extra jobs wait their turn.
5. The server runs indefinitely, starting all configured ZMQ subscribers from `zmq_subscription_list.json` and stopping them on shutdown.

## Main entry points

- `run_worker_pool(cfg: WorkerPoolConfig) -> None`
  - Loads subscriber configs and starts all `ZmqSubscriber` instances.
  - Registers the job handler on the configured `DEFAULT_JOB_TOPIC`.
  - Runs until SIGINT/SIGTERM, then stops subscribers.

## Configuration

### `WorkerPoolConfig`

- `max_concurrency: int`
  - Limits concurrent job execution in the asyncio loop.
  - Default: `max(1, (os.cpu_count() or 4) - 1)`

- `rcvtimeo_ms: int`
  - ZMQ subscriber receive timeout.
  - Default: `1000`

- `execution_timeout_s: float | None`
  - Default workflow execution timeout passed to `run_workflow`.
  - Default: `None` (when env var is unset/0)

- `subscription_list_path: str`
  - Path to `zmq_subscription_list.json`.
  - Default: `zmq_subscription_list.json` (relative)

### Environment variables

- `WORKFLOW_EXECUTION_TIMEOUT_S`
  - Default execution timeout (float). Use `0` to disable (treated as `None`).

- `WORKER_MAX_CONCURRENCY`
  - Max concurrency (int). Use `0` or unset to fall back to the default derived from CPU count.

## ZMQ subscriptions file: `zmq_subscription_list.json`

The server loads subscriptions from this JSON file (default: alongside the script).

Expected structure:

```json
{
  "subscriptions": [
    { "name": "...", "sub_endpoint": "tcp://...", "topic_idx": "0" }
  ],
  "topics": ["job", "result"]
}
```
Meaning:

- `topics`: array of topic names
  - The worker uses `topic_idx` from each subscription to select which single topic name that subscriber should connect to.
- Each subscription specifies:
  - `name`: label (used for logging)
  - `sub_endpoint`: ZMQ endpoint string (e.g., `tcp://host:port`)
  - `topic_idx`: index into the `topics` array (as an integer or numeric string)
- The worker attaches its job handler to `ZmqTopics().job` (the `DEFAULT_JOB_TOPIC`), not to an arbitrary topic string from this file.

## Job payload format (message body)

Jobs are JSON objects delivered to the job handler topic.

## Required fields

- `run_id` (string)
- Exactly one of the following:
  - `workflow_path` (string), OR
  - `workflow_graph` (object/dict)

## Optional fields

- `initial_inputs` (object/dict)
- `unit_param_overrides` (object/dict)
- `format` (string hint; forwarded as format_hint)
- `response_endpoint` (string)
  - If provided: the subprocess creates a `ZmqPublisher` and passes it into `run_workflow`.
  - `run_workflow` publishes streamed tokens + final result/error to ZMQ.
- `execution_timeout_s` (number)
  - If present: overrides `cfg.execution_timeout_s` for this job only.

## Validation behavior

Jobs are rejected (logged as errors) if:
- `run_id` is missing or not a string
- both/neither of `workflow_path` and `workflow_graph` are provided
- `initial_inputs` / `unit_param_overrides` are present but not objects/dicts
- `response_endpoint` is present but not a string
- `execution_timeout_s` is present but not a number

## Shutdown:

- SIGINT/SIGTERM set a stop event.
- All subscribers are stopped in `finally`.



It will:

- configure logging to stdout
- load `zmq_subscription_list.json` from the same directory as the script
- start ZMQ subscribers
- run until interrupted (Ctrl+C / SIGINT) or terminated (SIGTERM)
