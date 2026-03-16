"""
RL Coach assistant handler: build initial_inputs for rl_coach_workflow.json.

Chat runs the workflow via run_rl_coach_workflow(); no direct LLM calls.
Aligns with Workflow Designer: training config summary, training results (best model),
previous turn, and RAG context.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

_REPO_ROOT: Path | None = None
try:
    from gui.flet.components.settings import REPO_ROOT as _REPO_ROOT_SETTINGS, get_best_model_path, get_training_config_path
    _REPO_ROOT = _REPO_ROOT_SETTINGS
except ImportError:
    _REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
    def get_training_config_path() -> str:
        return str(_REPO_ROOT / "config" / "examples" / "training_config.yaml")
    def get_best_model_path() -> str:
        return ""


def get_training_config_summary() -> str:
    """
    Load training config from settings path and return a short summary for the prompt.
    Returns YAML snippet or a message if file missing/invalid.
    """
    path_str = (get_training_config_path() or "").strip()
    if not path_str:
        return "(No training config path set in settings.)"
    path = Path(path_str)
    if not path.is_absolute() and _REPO_ROOT is not None:
        path = (_REPO_ROOT / path_str).resolve()
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


def build_rl_coach_initial_inputs(
    user_message: str,
    training_config: str = "",
    training_results: str = "",
    previous_turn: str = "",
) -> dict[str, dict[str, Any]]:
    """
    Build initial_inputs for run_workflow(rl_coach_workflow.json).
    Same pattern as Workflow Designer: separate injects for user_message (string, also drives RAG),
    training_config, training_results, previous_turn. RAG context is produced inside the workflow
    (inject_user_message → RagSearch → Filter → FormatRagPrompt → Aggregate).
    """
    user_message = (user_message or "").strip() or "(No message provided.)"
    return {
        "inject_user_message": {"data": user_message},
        "inject_training_config": {"data": (training_config or "").strip()},
        "inject_training_results": {"data": (training_results or "").strip()},
        "inject_previous_turn": {"data": (previous_turn or "").strip()},
    }
