"""
Suggest a chat title filename from the user's first message via create_filename.json.

Inject → Prompt → LLMAgent; workflow path defaults from ``chat_name_creator`` role YAML
(``get_role_chat_workflow_path``); optional override via app settings. Prompt template path
still comes from app settings.
"""
from __future__ import annotations

from agents.roles.types import RoleConfig
from core.schemas.primitives import WorkflowInputs
from gui.components.settings import (
    get_create_filename_prompt_path,
    get_create_filename_workflow_path,
    get_workflow_designer_llm_generation_options,
)
from runtime.run import run_workflow


def _required_config_string(
    cfg: RoleConfig,
    key: str,
) -> str:
    try:
        value = getattr(cfg, key)
    except AttributeError as exc:
        raise ValueError(f"Unknown configuration value: {key}") from exc

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing or invalid configuration value: {key}")

    return value.strip()


def build_create_filename_unit_param_overrides(
    provider: str,
    cfg: RoleConfig,
) -> WorkflowInputs:
    """Build parameter overrides for the create_filename workflow."""
    model_name = _required_config_string(cfg, "model")
    host = _required_config_string(cfg, "host")

    provider_name = provider.strip()
    if not provider_name:
        raise ValueError("Provider cannot be empty")

    return {
        "llm_agent": {
            "model_name": model_name,
            "provider": provider_name,
            "host": host,
            "options": dict(
                get_workflow_designer_llm_generation_options()
            ),
        },
        "prompt_llm": {
            "template_path": str(get_create_filename_prompt_path()),
        },
    }


def run_create_filename_workflow(
    first_message: str,
    provider: str,
    cfg: RoleConfig | None,
    execution_timeout_s: float = 60.0,
) -> str:
    """
    Run the create_filename workflow to suggest a short snake_case filename.

    Returns raw model output; the caller should slugify it.
    Returns an empty string on error or when no role configuration is provided.
    """
    if cfg is None:
        return ""

    initial_inputs: WorkflowInputs = {
        "inject_user_message": {
            "data": {
                "user_message": (
                    "User's first message:\n"
                    f"{first_message.strip()}"
                ),
            },
        },
    }

    try:
        outputs = run_workflow(
            get_create_filename_workflow_path(),
            initial_inputs=initial_inputs,
            unit_param_overrides=(
                build_create_filename_unit_param_overrides(
                    provider=provider,
                    cfg=cfg,
                )
            ),
            format="dict",
            execution_timeout_s=execution_timeout_s,
        )

        llm_agent = outputs.get("llm_agent")
        if not isinstance(llm_agent, dict):
            return ""

        action = llm_agent.get("action")
        return action.strip() if isinstance(action, str) else ""

    except (OSError, ValueError, RuntimeError, TypeError):
        return ""
