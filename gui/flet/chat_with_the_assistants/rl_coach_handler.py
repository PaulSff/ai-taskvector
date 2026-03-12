"""
RL Coach assistant handler: build initial_inputs for rl_coach_workflow.json.

Chat runs the workflow via run_rl_coach_workflow(); no direct LLM calls.
"""
from __future__ import annotations

from typing import Any


def build_rl_coach_initial_inputs(
    user_message: str,
    rag_context: str | None = None,
    training_config: str = "",
) -> dict[str, dict[str, Any]]:
    """
    Build initial_inputs for run_workflow(rl_coach_workflow.json).
    The Prompt unit template uses {user_message}, {rag_context}, {training_config}.
    """
    user_message = (user_message or "").strip() or "(No message provided.)"
    return {
        "inject_user_message": {
            "data": {
                "user_message": user_message,
                "rag_context": (rag_context or "").strip(),
                "training_config": (training_config or "").strip(),
            },
        },
    }
