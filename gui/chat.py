"""
AI chat panel: call Workflow Designer or RL Coach via Ollama, parse JSON edit, apply and return result.
Used by gui/app.py for the right-side chat panel.
"""
import json
import re
from typing import Any

from assistants.prompts import RL_COACH_SYSTEM, WORKFLOW_DESIGNER_SYSTEM

# Timeout for Ollama chat (seconds). First request may load the model and take 30–120s on CPU.
OLLAMA_CHAT_TIMEOUT = 300
# Enough tokens for natural-language reply + JSON block (prompts ask for both).
OLLAMA_NUM_PREDICT = 1024


def _format_ollama_exception(e: Exception) -> str:
    msg = str(e).strip()
    low = msg.lower()

    # Common cases when Ollama isn't reachable
    if any(s in low for s in ["connection refused", "failed to connect", "cannot connect", "connection error"]):
        return (
            "Couldn't connect to Ollama. Make sure the Ollama app/service is running, then try again. "
            "Quick check: run `ollama list` in a terminal."
        )

    # Corrupt / incomplete model pull (llama.cpp loader)
    if "vocab only" in low or "skipping tensors" in low:
        return (
            "Ollama loaded only the vocabulary and skipped tensors — this usually means the model files are corrupt "
            "or incomplete. Re-pull the model, then test it:\n\n"
            "- `ollama rm <model>`\n"
            "- `ollama pull <model>`\n"
            "- `ollama run <model> \"hello\"`"
        )

    # Timeouts often happen while loading the model on first request
    if "timeout" in low or "timed out" in low:
        return (
            f"Request timed out ({OLLAMA_CHAT_TIMEOUT}s). Ollama may be loading the model (first request can take 1–2 min on CPU). "
            "Try again, or use a smaller model."
        )

    # Generic 500 from Ollama server
    if "500" in low or "internal server error" in low:
        return (
            "Ollama returned 500. This can happen if the prompt/context is too large, the model is failing to load, "
            "or inference is too slow. Try a smaller model (e.g. `llama3.2`) and consider re-pulling it."
        )

    return f"Ollama error: {msg}"


def _graph_summary(current_graph: Any) -> dict[str, Any]:
    """Reduce graph context to a small, LLM-friendly summary."""
    if isinstance(current_graph, dict):
        units = current_graph.get("units", []) or []
        conns = current_graph.get("connections", []) or []
        unit_summary = [
            {"id": u.get("id"), "type": u.get("type"), "controllable": bool(u.get("controllable", False))}
            for u in units
            if isinstance(u, dict)
        ]
        conn_summary = [
            {"from": c.get("from") or c.get("from_id"), "to": c.get("to") or c.get("to_id")}
            for c in conns
            if isinstance(c, dict)
        ]
        return {"units": unit_summary, "connections": conn_summary}

    # Pydantic ProcessGraph
    return {
        "units": [{"id": u.id, "type": u.type, "controllable": bool(u.controllable)} for u in current_graph.units],
        "connections": [{"from": c.from_id, "to": c.to_id} for c in current_graph.connections],
    }


def _training_config_summary(current_config: Any) -> dict[str, Any]:
    """Reduce training config context to a small summary (avoid huge dumps)."""
    cfg = current_config.model_dump() if hasattr(current_config, "model_dump") else dict(current_config)
    goal = cfg.get("goal") or {}
    rewards = cfg.get("rewards") or {}
    algo = cfg.get("algorithm")
    hyper = cfg.get("hyperparameters") or {}
    # Keep only the most useful bits for coaching
    return {
        "algorithm": algo,
        "goal": {k: goal.get(k) for k in ("type", "target_temp", "target_volume_ratio", "target_pressure_range") if k in goal},
        "rewards": {
            "preset": rewards.get("preset"),
            "weights": rewards.get("weights"),
            "rules": rewards.get("rules"),
        },
        "hyperparameters": {k: hyper.get(k) for k in ("learning_rate", "n_steps", "batch_size", "n_epochs") if k in hyper},
    }


def _extract_content(response: Any) -> str:
    """Get message content from Ollama response (dict or object). Always return a string.
    For thinking models, if content is empty we fall back to the thinking field so the user sees something.
    """
    try:
        msg = response.get("message", {}) if isinstance(response, dict) else getattr(response, "message", None)
        if msg is None:
            return ""
        if isinstance(msg, dict):
            content = msg.get("content") or msg.get("thinking") or ""
        else:
            content = getattr(msg, "content", None) or getattr(msg, "thinking", None) or ""
        return (content or "").strip() if content is not None else ""
    except Exception:
        return ""


def _parse_json_block(content: str) -> dict[str, Any] | None:
    """Extract JSON object from LLM response. Prefer ```json ... ``` block; else first {...}."""
    content = content.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if match:
        raw = match.group(1).strip()
    else:
        start = content.find("{")
        if start == -1:
            return None
        depth = 0
        end = start
        for i, c in enumerate(content[start:], start):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if depth != 0:
            return None
        raw = content[start : end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def chat_workflow_designer(
    user_message: str,
    current_graph: Any,
    model: str = "llama3.2",
) -> tuple[str, dict[str, Any] | None]:
    """
    Send user message to Workflow Designer (Ollama); parse graph edit JSON.
    current_graph: ProcessGraph or dict (current process graph).
    Returns (assistant_reply_text, edit_dict or None). edit_dict is for process_assistant_apply.
    """
    try:
        from ollama import Client
    except ImportError:
        return "Ollama is not installed. Install with: pip install ollama. Then start Ollama and pull a model (e.g. ollama pull llama3.2).", None

    ctx = json.dumps(_graph_summary(current_graph), indent=2)

    user_with_ctx = f"Current process graph (summary):\n{ctx}\n\nUser request: {user_message}"
    messages = [
        {"role": "system", "content": WORKFLOW_DESIGNER_SYSTEM},
        {"role": "user", "content": user_with_ctx},
    ]
    try:
        client = Client(timeout=OLLAMA_CHAT_TIMEOUT)
        response = client.chat(
            model=model,
            messages=messages,
            options={"temperature": 0.3, "num_predict": OLLAMA_NUM_PREDICT},
        )
        content = _extract_content(response)
    except Exception as e:
        return _format_ollama_exception(e), None

    edit = _parse_json_block(content)
    return (content or "(No response from model.)"), edit


def chat_rl_coach(
    user_message: str,
    current_config: Any,
    model: str = "llama3.2",
) -> tuple[str, dict[str, Any] | None]:
    """
    Send user message to RL Coach (Ollama); parse config edit JSON.
    current_config: TrainingConfig or dict.
    Returns (assistant_reply_text, edit_dict or None). edit_dict is for training_assistant_apply.
    """
    try:
        from ollama import Client
    except ImportError:
        return "Ollama is not installed. Install with: pip install ollama.", None

    ctx = json.dumps(_training_config_summary(current_config), indent=2)
    user_with_ctx = f"Current training config:\n{ctx}\n\nUser request: {user_message}"
    messages = [
        {"role": "system", "content": RL_COACH_SYSTEM},
        {"role": "user", "content": user_with_ctx},
    ]
    try:
        client = Client(timeout=OLLAMA_CHAT_TIMEOUT)
        response = client.chat(
            model=model,
            messages=messages,
            options={"temperature": 0.3, "num_predict": OLLAMA_NUM_PREDICT},
        )
        content = _extract_content(response)
    except Exception as e:
        return _format_ollama_exception(e), None

    edit = _parse_json_block(content)
    return (content or "(No response from model.)"), edit
