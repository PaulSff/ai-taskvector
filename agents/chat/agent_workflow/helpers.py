"""Initial inputs, overrides, runtime label, and apply-result refresh for agent chat workflows."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal

FormatProcess = Literal["dict", "yaml", "pyflow"]


def missing_workflow_msg(path: Path) -> str:
    return f"Required workflow file not found: {path}"


async def get_runtime_for_prompts(graph: Any) -> Literal["native", "external"]:
    from services.workflows.core_workflows import run_runtime_label

    def _log(msg: str) -> None:
        print(f"[get_runtime_for_prompts] {msg} ts={time.time():.3f}", flush=True)

    _log(f"enter graph_type={type(graph).__name__} graph_is_none={graph is None}")

    if graph is None:
        _log("graph_none -> external")
        return "external"

    r = graph.get("runtime") if isinstance(graph, dict) else getattr(graph, "runtime", None)
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
    prev: dict[str, Any] | None,
    graph: Any,
    *,
    supplement_summary: str = "",
) -> dict[str, Any]:
    prev = prev or {}

    from services.workflows.core_workflows import run_graph_summary

    if graph is not None and hasattr(graph, "model_dump"):
        g_dict = graph.model_dump(by_alias=True)
    elif isinstance(graph, dict):
        g_dict = graph
    else:
        g_dict = {"units": [], "connections": []}

    base = (prev.get("edits_summary") or "").strip()
    sup = (supplement_summary or "").strip()
    edits_summary = f"{base}; {sup}" if (base and sup) else (base or sup or "applied")

    graph_after = await run_graph_summary(g_dict)

    return {
        "attempted": True,
        "success": True,
        "error": None,
        "edits_summary": edits_summary,
        "graph_after": graph_after,
    }


def build_self_correction_retry_inputs(
    failed_apply_result: dict[str, Any],
    graph: Any,
    recent_changes: str | None,
    runtime: str = "native",
    coding_is_allowed: bool = True,
    contribution_is_allowed: bool | None = None,
    previous_turn: str = "",
    language_hint: str | None = None,
    session_language: str = "",
    *,
    analyst_mode: bool = False,
) -> dict[str, dict[str, Any]]:
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
    cfg: dict[str, Any],
    report_output_dir: str | None = None,
    *,
    prompt_template_path: str | Path | None = None,
    llm_options_role_id: str = "workflow_designer",
    rag_top_k_role_id: str = "workflow_designer",
) -> dict[str, dict[str, Any]]:
    # lazy imports to break cycle
    from gui.components.settings import (
        get_rag_format_max_chars,
        get_rag_format_snippet_max,
        get_rag_min_score,
        get_role_llm_generation_options,
        get_role_rag_top_k,
        get_workflow_designer_prompt_path,
    )

    model_name = (cfg.get("model") or "").strip() or "llama3.2"
    host = (cfg.get("host") or "http://127.0.0.1:11434").strip()
    _prompt = (
        str(Path(prompt_template_path).resolve())
        if prompt_template_path is not None
        else str(get_workflow_designer_prompt_path())
    )

    overrides: dict[str, dict[str, Any]] = {
        "llm_agent": {
            "model_name": model_name,
            "provider": (provider or "ollama").strip(),
            "host": host,
            "options": dict(get_role_llm_generation_options(llm_options_role_id)),
        },
        "rag_search": {"top_k": get_role_rag_top_k(rag_top_k_role_id)},
        "rag_filter": {"value": get_rag_min_score()},
        "format_rag": {
            "max_chars": get_rag_format_max_chars(),
            "snippet_max": get_rag_format_snippet_max(),
        },
        "prompt_llm": {"template_path": _prompt},
    }

    if report_output_dir:
        overrides["report"] = {"output_dir": report_output_dir}

    from agents.chat.handlers.prompt_delegate_tool_visibility import (
        merge_prompt_llm_strip_delegate_when_auto,
    )

    merge_prompt_llm_strip_delegate_when_auto(overrides, Path(_prompt))
    return overrides
