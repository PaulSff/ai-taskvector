"""
RL Coach assistant handler: build initial_inputs for rl_coach_workflow.json.

Chat runs the workflow via run_rl_coach_workflow() (delegates to run_assistant_workflow).
Aligns with Workflow Designer / Analyst: graph + follow-up injects, training summary, RAG,
merge_response contract, and parser-output follow-ups.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from assistants.roles import RL_COACH_ROLE_ID
from assistants.roles.rl_coach.workflow_inputs import build_rl_coach_initial_inputs
from assistants.roles.workflow_path import get_role_chat_workflow_path
from gui.chat.handlers.prompt_delegate_tool_visibility import merge_prompt_llm_strip_delegate_when_auto
from gui.chat.handlers.workflow_designer_handler import run_assistant_workflow
from gui.components.settings import (
    REPO_ROOT,
    get_best_model_path,
    get_rag_format_max_chars,
    get_rag_format_snippet_max,
    get_rag_min_score,
    get_rl_coach_llm_generation_options,
    get_rl_coach_prompt_path,
    get_role_rag_top_k,
    get_training_config_path,
)

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
    *,
    report_output_dir: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Build unit_param_overrides for rl_coach_workflow.json (LLM, prompt, RAG caps, optional report dir)."""
    model_name = (cfg.get("model") or "").strip() or "llama3.2"
    host = (cfg.get("host") or "http://127.0.0.1:11434").strip()
    _prompt = str(get_rl_coach_prompt_path())
    overrides: dict[str, dict[str, Any]] = {
        "llm_agent": {
            "model_name": model_name,
            "provider": (provider or "ollama").strip(),
            "host": host,
            "options": dict(get_rl_coach_llm_generation_options()),
        },
        "rag_search": {
            "top_k": get_role_rag_top_k(RL_COACH_ROLE_ID),
        },
        "rag_filter": {
            "value": get_rag_min_score(),
        },
        "format_rag": {
            "max_chars": get_rag_format_max_chars(),
            "snippet_max": get_rag_format_snippet_max(),
        },
        "prompt_llm": {"template_path": _prompt},
    }
    if report_output_dir:
        overrides["report"] = {"output_dir": report_output_dir}
    merge_prompt_llm_strip_delegate_when_auto(overrides, Path(_prompt))
    return overrides


def run_rl_coach_workflow(
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    execution_timeout_s: float | None = DEFAULT_RL_COACH_EXECUTION_TIMEOUT_S,
    stream_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Run rl_coach_workflow.json via run_assistant_workflow (merge_response.data shape).

    Returns reply, result, status, parser_output, workflow_errors, and other merge_response keys.
    Training save: when ``result.kind == applied``, use ``result.config`` as applied_config (caller).
    """
    return run_assistant_workflow(
        initial_inputs,
        unit_param_overrides=unit_param_overrides,
        execution_timeout_s=execution_timeout_s,
        stream_callback=stream_callback,
        workflow_path=RL_COACH_WORKFLOW_PATH,
    )
