"""
ComfyUI RL bridge: exposes /step endpoint that drives ComfyUI workflow execution.

Usage:
  python -m server.comfyui_bridge --workflow workflow.json --port 8189 --comfy-url http://127.0.0.1:8188

The bridge accepts the same step protocol as Node-RED:
  POST /step { "action": [float, ...] } -> { "observation": [...], "reward": float, "done": bool }
  POST /step { "reset": true } -> { "observation": [...], "reward": 0, "done": false }

Workflow must be built from ProcessGraph export (canonical topology with step_driver and step_rewards; RLOracle added via add_pipeline).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path


def _comfyui_workflow_to_api(workflow: dict) -> dict:
    """Convert ComfyUI workflow (nodes+links) to API prompt format (flat node dict)."""
    nodes = workflow.get("nodes") or []
    links = workflow.get("links") or []
    link_to_conn: dict[int, tuple[str, int, str, int]] = {}
    for lnk in links:
        if not isinstance(lnk, dict):
            continue
        lid = lnk.get("id")
        oid = lnk.get("origin_id")
        oslot = lnk.get("origin_slot", 0)
        tid = lnk.get("target_id")
        tslot = lnk.get("target_slot", 0)
        if lid is not None and oid is not None and tid is not None:
            link_to_conn[int(lid)] = (str(oid), int(oslot), str(tid), int(tslot))

    prompt: dict[str, dict] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id", ""))
        ntype = n.get("type") or n.get("class_type")
        if not nid or not ntype:
            continue
        inputs: dict[str, object] = {}
        for inp in n.get("inputs") or []:
            if not isinstance(inp, dict):
                continue
            name = inp.get("name")
            link = inp.get("link")
            if name is not None and link is not None and link in link_to_conn:
                oid, oslot, _, _ = link_to_conn[link]
                inputs[str(name)] = [oid, int(oslot)]
        wv = n.get("widgets_values")
        if isinstance(wv, (list, tuple)):
            for i, v in enumerate(wv):
                inputs[f"widget_{i}"] = v
        elif isinstance(wv, dict):
            inputs.update(wv)
        prompt[nid] = {"class_type": str(ntype), "inputs": inputs}
    return prompt


def _queue_and_wait(
    comfy_url: str,
    workflow: dict,
    client_id: str = "rl_bridge",
    timeout: float = 120.0,
    poll_interval: float = 0.2,
) -> dict:
    api_prompt = _comfyui_workflow_to_api(workflow)
    body = {"prompt": api_prompt, "client_id": client_id}
    req = urllib.request.Request(
        comfy_url.rstrip("/") + "/prompt",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    prompt_id = data.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI /prompt failed: {data}")

    start = time.time()
    while time.time() - start < timeout:
        hist_req = urllib.request.Request(
            comfy_url.rstrip("/") + "/history/" + prompt_id,
            method="GET",
        )
        with urllib.request.urlopen(hist_req, timeout=10) as resp:
            hist = json.loads(resp.read().decode())
        if prompt_id in hist:
            return hist[prompt_id]
        time.sleep(poll_interval)
    raise TimeoutError(f"ComfyUI execution timed out after {timeout}s")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="ComfyUI RL step bridge")
    parser.add_argument("--workflow", required=True, help="Path to ComfyUI workflow JSON")
    parser.add_argument("--port", type=int, default=8189, help="Bridge HTTP port")
    parser.add_argument("--comfy-url", default="http://127.0.0.1:8188", help="ComfyUI server URL")
    parser.add_argument("--action-file", default="/tmp/comfyui_rl_action.json")
    parser.add_argument("--result-file", default="/tmp/comfyui_rl_result.json")
    args = parser.parse_args()

    workflow_path = Path(args.workflow)
    if not workflow_path.exists():
        print(f"Workflow not found: {workflow_path}", file=sys.stderr)
        sys.exit(1)
    workflow = json.loads(workflow_path.read_text())

    action_file = args.action_file
    result_file = args.result_file
    os.environ["COMFYUI_RL_ACTION_FILE"] = action_file
    os.environ["COMFYUI_RL_RESULT_FILE"] = result_file

    from http.server import HTTPServer, BaseHTTPRequestHandler

    comfy_url = args.comfy_url
    port = args.port

    class StepHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path != "/step":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body.decode())
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return
            if data.get("reset"):
                step_data = {"action": []}
            else:
                step_data = {"action": data.get("action", [])}
            try:
                Path(action_file).write_text(json.dumps(step_data))
            except OSError as e:
                self.send_error(500, str(e))
                return
            try:
                _queue_and_wait(comfy_url, workflow)
            except Exception as e:
                self.send_error(502, str(e))
                return
            try:
                result = json.loads(Path(result_file).read_text())
            except (OSError, json.JSONDecodeError):
                result = {"observation": [0.0], "reward": 0.0, "done": False}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())

        def log_message(self, format: str, *args: object) -> None:
            print(args[0] if args else "")

    server = HTTPServer(("", port), StepHandler)
    print(f"ComfyUI RL bridge listening on port {port}, ComfyUI at {comfy_url}")
    print(f"  POST /step {{ \"action\": [...] }} or {{ \"reset\": true }}")
    server.serve_forever()


if __name__ == "__main__":
    main()
