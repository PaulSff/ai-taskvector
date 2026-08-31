"""Agent (role) workflow units param overrides"""

from __future__ import annotations

from pathlib import Path

from core.schemas.primitives import WorkflowInputs


def build_agent_workflow_unit_param_overrides(
    provider: str,
    report_output_dir: str | None = None,
    *,
    model_name: str,
    host: str,
    prompt_template_path: str | Path | None = None,
    llm_options_role_id: str,
    rag_top_k_role_id: str,
) -> WorkflowInputs:
    # lazy imports to break cycle
    from gui.components.settings import (
        get_rag_format_max_chars,
        get_rag_format_snippet_max,
        get_rag_min_score,
        get_role_llm_generation_options,
        get_role_rag_top_k,
        get_workflow_designer_prompt_path,
    )

    prompt_path = (
        Path(prompt_template_path).resolve()
        if prompt_template_path is not None
        else Path(get_workflow_designer_prompt_path()).resolve()
    )

    overrides: WorkflowInputs = {
        "llm_agent": {
            "model_name": model_name,
            "provider": provider,
            "host": host,
            "options": dict(
                get_role_llm_generation_options(llm_options_role_id)
            ),
        },
        "rag_search": {
            "top_k": get_role_rag_top_k(rag_top_k_role_id),
        },
        "rag_filter": {
            "value": get_rag_min_score(),
        },
        "format_rag": {
            "max_chars": get_rag_format_max_chars(),
            "snippet_max": get_rag_format_snippet_max(),
        },
        "prompt_llm": {
            "template_path": str(prompt_path),
        },
    }

    if report_output_dir:
        overrides["report"] = {
            "output_dir": report_output_dir,
        }

    from agents.chat.handlers.prompt_delegate_tool_visibility import (
        merge_prompt_llm_strip_delegate_when_auto,
    )

    merge_prompt_llm_strip_delegate_when_auto(overrides, prompt_path)

    return overrides
