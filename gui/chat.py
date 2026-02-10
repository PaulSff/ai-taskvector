"""
AI chat panel: call Workflow Designer or RL Coach via a provider-agnostic LLM integration,
parse JSON edit, apply and return result.

Used by gui/app.py for the right-side chat panel.
"""
import json
import re
from typing import Any

from assistants.prompts import RL_COACH_SYSTEM, WORKFLOW_DESIGNER_SYSTEM
from LLM_integrations import client as llm_client
from gui.flet.components.settings import get_llm_provider, get_llm_provider_config

# Timeout for LLM chat (seconds). First request may load the model and take 30–120s on CPU.
OLLAMA_CHAT_TIMEOUT = 300
# Enough tokens for natural-language reply + JSON block (prompts ask for both).
OLLAMA_NUM_PREDICT = 1024
# Max number of prior user/assistant turn pairs to include in context (to avoid overflowing the model context).
OLLAMA_CHAT_HISTORY_TURNS = 10


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


def _chat_history_to_messages(chat_history: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Convert chat_messages (from UI) to Ollama API format. Uses only role and content; caps length."""
    out: list[dict[str, str]] = []
    # Include only the last N turns to avoid context overflow
    turns = chat_history[-(OLLAMA_CHAT_HISTORY_TURNS * 2) :] if len(chat_history) > OLLAMA_CHAT_HISTORY_TURNS * 2 else chat_history
    for msg in turns:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content") or ""
        if isinstance(content, str):
            out.append({"role": role, "content": content})
    return out


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
    chat_history: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """
    Send user message to Workflow Designer (Ollama); parse graph edit JSON.
    current_graph: ProcessGraph or dict (current process graph).
    chat_history: optional list of prior messages (e.g. from st.session_state.chat_messages) for context.
    Returns (assistant_reply_text, edit_dict or None). edit_dict is for process_assistant_apply.
    """
    provider = get_llm_provider(assistant="workflow_designer")
    cfg: dict[str, Any] = dict(get_llm_provider_config(assistant="workflow_designer") or {})
    # Back-compat: allow caller to override model for providers that accept it.
    if model:
        cfg.setdefault("model", model)

    ctx = json.dumps(_graph_summary(current_graph), indent=2)
    user_with_ctx = f"Current process graph (summary):\n{ctx}\n\nUser request: {user_message}"

    messages: list[dict[str, str]] = [{"role": "system", "content": WORKFLOW_DESIGNER_SYSTEM}]
    if chat_history:
        messages.extend(_chat_history_to_messages(chat_history))
    messages.append({"role": "user", "content": user_with_ctx})
    try:
        content = llm_client.chat(
            provider=provider,
            config=cfg,
            messages=messages,
            timeout_s=OLLAMA_CHAT_TIMEOUT,
            options={"temperature": 0.3, "num_predict": OLLAMA_NUM_PREDICT},
        )
    except Exception as e:
        return llm_client.format_exception(provider=provider, e=e), None

    edit = _parse_json_block(content)
    return (content or "(No response from model.)"), edit


def chat_rl_coach(
    user_message: str,
    current_config: Any,
    model: str = "llama3.2",
    chat_history: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """
    Send user message to RL Coach (Ollama); parse config edit JSON.
    current_config: TrainingConfig or dict.
    chat_history: optional list of prior messages for context.
    Returns (assistant_reply_text, edit_dict or None). edit_dict is for training_assistant_apply.
    """
    provider = get_llm_provider(assistant="rl_coach")
    cfg: dict[str, Any] = dict(get_llm_provider_config(assistant="rl_coach") or {})
    if model:
        cfg.setdefault("model", model)

    ctx = json.dumps(_training_config_summary(current_config), indent=2)
    user_with_ctx = f"Current training config:\n{ctx}\n\nUser request: {user_message}"

    messages: list[dict[str, str]] = [{"role": "system", "content": RL_COACH_SYSTEM}]
    if chat_history:
        messages.extend(_chat_history_to_messages(chat_history))
    messages.append({"role": "user", "content": user_with_ctx})
    try:
        content = llm_client.chat(
            provider=provider,
            config=cfg,
            messages=messages,
            timeout_s=OLLAMA_CHAT_TIMEOUT,
            options={"temperature": 0.3, "num_predict": OLLAMA_NUM_PREDICT},
        )
    except Exception as e:
        return llm_client.format_exception(provider=provider, e=e), None

    edit = _parse_json_block(content)
    return (content or "(No response from model.)"), edit
