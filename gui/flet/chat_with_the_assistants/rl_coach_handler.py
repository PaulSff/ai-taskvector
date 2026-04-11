"""
RL Coach assistant handler: build initial_inputs for rl_coach_workflow.json.

Chat runs the workflow via run_rl_coach_workflow(); no direct LLM calls.
Aligns with Workflow Designer: training config summary, training results (best model),
previous turn, and RAG context.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from assistants.roles import RL_COACH_ROLE_ID
from assistants.roles.rl_coach.workflow_inputs import build_rl_coach_initial_inputs
from assistants.roles.workflow_path import get_role_chat_workflow_path
from gui.flet.chat_with_the_assistants.workflow_run_utils import collect_workflow_errors
from gui.flet.components.settings import (
    REPO_ROOT,
    get_best_model_path,
    get_rl_coach_llm_generation_options,
    get_rl_coach_prompt_path,
    get_training_config_path,
)
from runtime.run import run_workflow

RL_COACH_WORKFLOW_PATH = get_role_chat_workflow_path(RL_COACH_ROLE_ID)
DEFAULT_RL_COACH_EXECUTION_TIMEOUT_S = 300.0


def get_training_config_summary() -> str:
    """
    Load training config from settings path and return a short summary for the prompt.
    Returns YAML snippet or a message if file missing/invalid.
    """
    path_str = (get_training_config_path() or "").strip()
    if not path_str:
        return "(No training config path set in settings.)"
    path = Path(path_str)
    if not path.is_absolute():
        path = (REPO_ROOT / path_str).resolve()
    if not path.is_file():
        return f"(Training config file not found: {path_str})"
    try:
        from core.normalizer import load_training_config_from_file
        cfg = load_training_config_from_file(path)
        if cfg is None:
            return f"(Could not parse training config: {path_str})"
        # Summary: goal, rewards (formula/rules), callbacks.best_model_save_path, hyperparameters
        parts = []
        if cfg.goal:
            parts.append(f"goal: {cfg.goal.model_dump()}")
        if cfg.rewards:
            r = cfg.rewards
            if r.formula:
                parts.append(f"rewards.formula: {r.formula}")
            if r.rules:
                parts.append(f"rewards.rules: {[x.model_dump() for x in r.rules]}")
        if cfg.callbacks:
            parts.append(f"callbacks.best_model_save_path: {cfg.callbacks.best_model_save_path}")
        if cfg.hyperparameters:
            parts.append(f"hyperparameters: {cfg.hyperparameters}")
        if not parts:
            return path.read_text(encoding="utf-8")[:2000]
        return "\n".join(parts)
    except Exception as e:
        return f"(Error loading config: {e})"


def get_training_results_follow_up() -> str:
    """
    Return a short "current training results" block for the prompt (best model path from settings).
    """
    path = (get_best_model_path() or "").strip()
    if path:
        return f"Current best model path (from latest training): {path}"
    return "No training run completed yet (no best model path in settings)."


def get_training_config_dict() -> dict[str, Any]:
    """
    Load training config from settings path and return as dict for ApplyTrainingConfigEdits.
    Returns empty dict if file missing or invalid.
    """
    path_str = (get_training_config_path() or "").strip()
    if not path_str:
        return {}
    path = Path(path_str)
    if not path.is_absolute():
        path = (REPO_ROOT / path_str).resolve()
    if not path.is_file():
        return {}
    try:
        from core.normalizer import load_training_config_from_file
        cfg = load_training_config_from_file(path)
        if cfg is None:
            return {}
        return cfg.model_dump(by_alias=True)
    except Exception:
        return {}


def build_rl_coach_unit_param_overrides(
    provider: str,
    cfg: dict[str, Any],
    rag_persist_dir: str = "",
    rag_embedding_model: str = "",
) -> dict[str, dict[str, Any]]:
    """Build unit_param_overrides for run_workflow(rl_coach_workflow.json): llm_agent, prompt_llm, rag_search (RAG pipeline)."""
    model_name = (cfg.get("model") or "").strip() or "llama3.2"
    host = (cfg.get("host") or "http://127.0.0.1:11434").strip()
    overrides: dict[str, dict[str, Any]] = {
        "llm_agent": {
            "model_name": model_name,
            "provider": (provider or "ollama").strip(),
            "host": host,
            "options": dict(get_rl_coach_llm_generation_options()),
        },
        "prompt_llm": {"template_path": str(get_rl_coach_prompt_path())},
    }
    if rag_persist_dir or rag_embedding_model:
        overrides["rag_search"] = {
            "persist_dir": (rag_persist_dir or "").strip(),
            "embedding_model": (rag_embedding_model or "").strip(),
        }
    return overrides


def run_rl_coach_workflow(
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    execution_timeout_s: float | None = DEFAULT_RL_COACH_EXECUTION_TIMEOUT_S,
    stream_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Run rl_coach_workflow.json and return reply for the GUI.
    Returns dict with keys: reply (str), workflow_errors (list of (unit_id, message)), applied_config.
    """
    try:
        from units.data_bi import register_data_bi_units

        register_data_bi_units()
    except Exception:
        pass
    outputs = run_workflow(
        RL_COACH_WORKFLOW_PATH,
        initial_inputs=initial_inputs,
        unit_param_overrides=unit_param_overrides,
        format="dict",
        execution_timeout_s=execution_timeout_s,
        stream_callback=stream_callback,
    )
    action = (outputs.get("llm_agent") or {}).get("action")
    reply = (action or "").strip() if isinstance(action, str) else ""
    process_out = outputs.get("process") or {}
    result = process_out.get("result") or {}
    applied_config = None
    if result.get("kind") == "applied":
        applied_config = process_out.get("config")
    return {
        "reply": reply,
        "workflow_errors": collect_workflow_errors(outputs),
        "applied_config": applied_config,
    }
