"""
Suggest a chat title filename from the user's first message via create_filename.json.

Inject → Prompt → LLMAgent; workflow path defaults from ``chat_name_creator`` role YAML
(``get_role_chat_workflow_path``); optional override via app settings. Prompt template path
still comes from app settings.
"""
from __future__ import annotations

from agents.chat.agent_workflow.build_units_param_overrides import (
    build_agent_workflow_unit_param_overrides,
)
from agents.chat.agent_workflow.paths import DEFAULT_EXECUTION_TIMEOUT_S
from config.settings import (
    get_create_filename_workflow_path,
)
from core.schemas.primitives import WorkflowInputs
from runtime.run import run_workflow


def run_create_filename_workflow(
    first_message: str,
    role_id: str,
) -> str:
    """
    Run the create_filename workflow to suggest a short snake_case filename.

    Returns raw model output; the caller should slugify it.
    Returns an empty string on error or when no role configuration is provided.
    """

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
                build_agent_workflow_unit_param_overrides(
                    role_id=role_id,
                )
            ),
            format="dict",
            execution_timeout_s=DEFAULT_EXECUTION_TIMEOUT_S,
            role_id=role_id,
        )

        llm_agent = outputs.get("llm_agent")
        if not isinstance(llm_agent, dict):
            return ""

        action = llm_agent.get("action")
        return action.strip() if isinstance(action, str) else ""

    except (OSError, ValueError, RuntimeError, TypeError) as exc:
        print(
                    f"run_create_filename_workflow failed: "
                    f"{type(exc).__name__}: {exc}"
                )
        return ""
