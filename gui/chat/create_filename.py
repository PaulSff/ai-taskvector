"""
Suggest a chat title filename from the user's first message via create_filename.json.

Inject → Prompt → LLMAgent; workflow path defaults from ``chat_name_creator`` role YAML
(``get_role_chat_workflow_path``); optional override via app settings. Prompt template path
still comes from app settings.
"""
from __future__ import annotations

from typing import Any

from gui.components.settings import (
    get_create_filename_prompt_path,
    get_create_filename_workflow_path,
    get_workflow_designer_llm_generation_options,
)
from runtime.run import run_workflow


def build_create_filename_unit_param_overrides(
    provider: str,
    cfg: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Build unit_param_overrides for run_workflow(create_filename.json): llm_agent and prompt_llm (template_path from settings)."""
    model_name = (cfg.get("model") or "").strip() or "llama3.2"
    host = (cfg.get("host") or "http://127.0.0.1:11434").strip()
    return {
        "llm_agent": {
            "model_name": model_name,
            "provider": (provider or "ollama").strip(),
            "host": host,
            "options": dict(get_workflow_designer_llm_generation_options()),
        },
        "prompt_llm": {"template_path": str(get_create_filename_prompt_path())},
    }


def run_create_filename_workflow(
    first_message: str,
    provider: str,
    cfg: dict[str, Any] | None,
    execution_timeout_s: float = 60.0,
) -> str:
    """
    Run create_filename.json workflow to suggest a short snake_case filename from the user's first message.
    Returns raw model output; caller should slugify. Returns empty string on error.
    """
    cfg = cfg or {}
    initial_inputs = {
        "inject_user_message": {
            "data": {"user_message": f"User's first message:\n{(first_message or '').strip()}"},
        },
    }
    overrides = build_create_filename_unit_param_overrides(provider, cfg)
    try:
        outputs = run_workflow(
            get_create_filename_workflow_path(),
            initial_inputs=initial_inputs,
            unit_param_overrides=overrides,
            format="dict",
            execution_timeout_s=execution_timeout_s,
        )
        action = (outputs.get("llm_agent") or {}).get("action")
        return (action or "").strip() if isinstance(action, str) else ""
    except Exception:
        return ""
