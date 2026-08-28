"""Initial inputs, overrides, runtime label, and apply-result refresh for agent chat workflows."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from core.graph.summary import graph_summary
from core.schemas.primitives import JsonObject, WorkflowInputs
from gui.components.workflow_tab.process_graph import ProcessGraph


def missing_workflow_msg(path: Path) -> str:
    return f"Required workflow file not found: {path}"


async def get_runtime_for_prompts(graph: JsonObject | None) -> Literal["native", "external"]:
    from services.workflows.core_workflows import run_runtime_label

    def _log(msg: str) -> None:
        print(f"[get_runtime_for_prompts] {msg} ts={time.time():.3f}", flush=True)

    _log(f"enter graph_type={type(graph).__name__} graph_is_none={graph is None}")

    if graph is None:
        _log("graph_none -> external")
        return "external"

    r = graph.get("runtime")
    _log(f"read_runtime_field r={r!r}")

    if r in ("native", "external"):
        _log(f"runtime_field_valid -> {r}")
        return r

    _log("runtime_field_invalid_or_missing -> run_runtime_label(graph)")
    t0 = time.time()
    _, is_native = await run_runtime_label(graph)
    _log(f"run_runtime_label_done dt={(time.time() - t0):.3f}s is_native={is_native}")

    out = "native" if is_native else "external"
    _log(f"return {out}")
    return out


async def refresh_last_apply_result_after_canvas_apply(
    prev: dict[str, object] | None,
    graph: ProcessGraph,
    *,
    supplement_summary: str = "",
) -> dict[str, object]:
    previous = prev or {}

    base = str(previous.get("edits_summary") or "").strip()
    supplement = supplement_summary.strip()

    edits_summary = (
        f"{base}; {supplement}"
        if base and supplement
        else base or supplement or "applied"
    )

    graph_after = graph_summary(graph)

    return {
        "attempted": True,
        "success": True,
        "error": None,
        "edits_summary": edits_summary,
        "graph_after": graph_after,
    }


async def validate_graph_to_apply_for_canvas_async(
    graph: ProcessGraph | None,
) -> tuple[ProcessGraph | None, str | None]:
    if graph is None:
        return None, "ValidateGraphToApply: graph missing"

    try:
        validated_graph = ProcessGraph.model_validate(
            graph.model_dump(by_alias=True)
        )
    except ValidationError as exc:
        return None, f"ValidateGraphToApply: invalid graph: {exc}"

    return validated_graph, None


def build_self_correction_retry_inputs(
    failed_apply_result: dict[str, object],
    graph: ProcessGraph,
    recent_changes: str | None,
    runtime: str = "native",
    coding_is_allowed: bool = True,
    contribution_is_allowed: bool | None = None,
    previous_turn: str = "",
    language_hint: str | None = None,
    session_language: str = "",
    *,
    analyst_mode: bool = False,
) -> WorkflowInputs:
    # lazy imports to break cycle
    from agents.prompts import WORKFLOW_DESIGNER_RETRY_USER
    from agents.roles.workflow_designer.workflow_inputs import (
        build_agent_workflow_initial_inputs,
        default_wf_language_hint,
    )

    err_str = str(failed_apply_result.get("error", "Unknown"))[:500]
    if language_hint is None:
        language_hint = default_wf_language_hint(session_language)
    lang = (language_hint or "English (en)").strip() or "English (en)"
    retry_user_message = WORKFLOW_DESIGNER_RETRY_USER.format(
        error=err_str,
        language=lang,
        session_language=session_language,
    )

    # keep the existing behavior; this function used to import get_contribution_is_allowed
    from gui.components.settings import get_contribution_is_allowed

    _contrib = get_contribution_is_allowed() if contribution_is_allowed is None else contribution_is_allowed

    return build_agent_workflow_initial_inputs(
        retry_user_message,
        graph,
        failed_apply_result,
        recent_changes,
        follow_up_context="",
        runtime=runtime,
        coding_is_allowed=coding_is_allowed,
        contribution_is_allowed=_contrib,
        previous_turn=(previous_turn or "").strip(),
        language_hint=lang,
        session_language=session_language,
        analyst_mode=analyst_mode,
    )


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
