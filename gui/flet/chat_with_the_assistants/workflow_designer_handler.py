"""
Workflow Designer assistant handler: build initial_inputs and run assistant_workflow.json.

Chat runs the workflow via run_assistant_workflow(); prompt and response handling live in the workflow.
The user's message is passed in initial_inputs["inject_user_message"]["data"] and is required for the LLM.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from units.semantics.language_detector.language_detector import detect_language_for_prompt

from assistants.prompts import (
    WORKFLOW_DESIGNER_ADD_CODE_BLOCK_LINE,
    WORKFLOW_DESIGNER_ADD_ENVIRONMENT_LINE,
    WORKFLOW_DESIGNER_AI_TRAINING_EXTERNAL,
    WORKFLOW_DESIGNER_AI_TRAINING_NATIVE,
    WORKFLOW_DESIGNER_CODING_LINE,
    WORKFLOW_DESIGNER_DEBUGGING_LINE,
    WORKFLOW_DESIGNER_DO_NOT_REPEAT,
    WORKFLOW_DESIGNER_RECENT_CHANGES_PREFIX,
    WORKFLOW_DESIGNER_RETRY_USER,
    WORKFLOW_DESIGNER_RUN_WORKFLOW_LINE,
    WORKFLOW_DESIGNER_RUNNING_FLOW_LINE,
    WORKFLOW_DESIGNER_SELF_CORRECTION,
    WORKFLOW_DESIGNER_TURN_STATE_PREFIX,
)
from core.schemas.process_graph import ProcessGraph
from gui.flet.components.workflow.core_workflows import run_normalize_graph
from runtime.executor import GraphExecutor
from runtime.run import run_workflow, WorkflowTimeoutError

try:
    from gui.flet.components.settings import (
        get_assistant_workflow_path,
        get_browser_workflow_path,
        get_create_filename_prompt_path,
        get_create_filename_workflow_path,
        get_github_get_workflow_path,
        get_rl_coach_prompt_path,
        get_rl_coach_workflow_path,
        get_web_search_workflow_path,
        get_workflow_designer_prompt_path,
    )
except ImportError:
    _FALLBACK_ROOT = Path(__file__).resolve().parent.parent.parent.parent
    _FALLBACK_DIR = _FALLBACK_ROOT / "assistants"
    _FALLBACK_WORKFLOW_DIR = _FALLBACK_ROOT / "gui" / "flet" / "components" / "workflow"
    _PROMPTS_DIR = _FALLBACK_ROOT / "config" / "prompts"
    def get_assistant_workflow_path():
        return _FALLBACK_DIR / "assistant_workflow.json"
    def get_web_search_workflow_path():
        return _FALLBACK_WORKFLOW_DIR / "tools" / "web_search.json"
    def get_browser_workflow_path():
        return _FALLBACK_WORKFLOW_DIR / "tools" / "browser.json"
    def get_github_get_workflow_path():
        return _FALLBACK_WORKFLOW_DIR / "tools" / "github_get.json"
    def get_workflow_designer_prompt_path():
        return _PROMPTS_DIR / "workflow_designer.json"
    def get_rl_coach_prompt_path():
        return _PROMPTS_DIR / "rl_coach.json"
    def get_create_filename_workflow_path():
        return _FALLBACK_DIR / "create_filename.json"
    def get_create_filename_prompt_path():
        return _PROMPTS_DIR / "create_filename.json"
    def get_rl_coach_workflow_path():
        return _FALLBACK_DIR / "rl_coach_workflow.json"

# All paths from app settings (config/app_settings.json)
ASSISTANT_WORKFLOW_PATH = get_assistant_workflow_path()
CREATE_FILENAME_WORKFLOW_PATH = get_create_filename_workflow_path()
RL_COACH_WORKFLOW_PATH = get_rl_coach_workflow_path()
WEB_SEARCH_WORKFLOW_PATH = get_web_search_workflow_path()
BROWSER_WORKFLOW_PATH = get_browser_workflow_path()
GITHUB_GET_WORKFLOW_PATH = get_github_get_workflow_path()

# Timeout for workflow run so we don't hang when a unit (LLM, RAG, etc.) never responds. Timeout then drop.
DEFAULT_EXECUTION_TIMEOUT_S = 300.0


def collect_workflow_errors(outputs: dict[str, Any]) -> list[tuple[str, str]]:
    """
    Collect non-null error port values from workflow outputs.
    Returns [(unit_id, error_message), ...] for units that emitted an error.
    """
    errors: list[tuple[str, str]] = []
    if not isinstance(outputs, dict):
        return errors
    for unit_id, unit_out in outputs.items():
        if not isinstance(unit_out, dict):
            continue
        err = unit_out.get("error")
        if err is None:
            continue
        if isinstance(err, str) and err.strip():
            errors.append((unit_id, err.strip()))
    return errors


def run_workflow_with_errors(
    path: str | Path,
    initial_inputs: dict[str, dict[str, Any]] | None = None,
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    format: str | None = "dict",
    execution_timeout_s: float | None = None,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """
    Run a workflow and return (outputs, errors). Error collection is done here so
    callers (e.g. chat) only need to display errors (toast), not import collect_workflow_errors.
    execution_timeout_s: if set, abort after this many seconds (raises WorkflowTimeoutError).
    """
    outputs = run_workflow(
        path,
        initial_inputs=initial_inputs or {},
        unit_param_overrides=unit_param_overrides,
        format=format,
        execution_timeout_s=execution_timeout_s,
    )
    return outputs, collect_workflow_errors(outputs)


def _build_turn_state_string(last_apply_result: dict[str, Any] | None) -> str:
    """Build the turn state line for inject_turn_state (e.g. 'Turn state: Last action: none.')."""
    if last_apply_result is None:
        return WORKFLOW_DESIGNER_TURN_STATE_PREFIX + "Last action: none."
    if last_apply_result.get("success") is False:
        err = last_apply_result.get("error") or "Unknown error"
        return WORKFLOW_DESIGNER_TURN_STATE_PREFIX + f"Last action: failed (error: {err})."
    summary = last_apply_result.get("edits_summary") or ""
    if summary:
        return WORKFLOW_DESIGNER_TURN_STATE_PREFIX + f"Last action: applied successfully ({summary})."
    return WORKFLOW_DESIGNER_TURN_STATE_PREFIX + "Last action: applied successfully."


def _build_last_edit_block_string(
    last_apply_result: dict[str, Any] | None,
    self_correction_template: str = WORKFLOW_DESIGNER_SELF_CORRECTION,
    *,
    language: str = "English (en)",
) -> str:
    """Build the last-edit paragraph for inject_last_edit_block (failed/applied or empty)."""
    if last_apply_result is None:
        return ""
    if last_apply_result.get("success") is False:
        error_msg = last_apply_result.get("error") or "Unknown error"
        try:
            sc_text = self_correction_template.format(error=error_msg, language=language)
        except KeyError:
            sc_text = self_correction_template.format(error=error_msg)
        return "Last edit failed. " + sc_text + "\n" + WORKFLOW_DESIGNER_DO_NOT_REPEAT
    summary = last_apply_result.get("edits_summary") or ""
    if summary:
        return "Last edit applied successfully. Applied: " + summary + "\n" + WORKFLOW_DESIGNER_DO_NOT_REPEAT
    return "Last edit applied successfully.\n" + WORKFLOW_DESIGNER_DO_NOT_REPEAT


def refresh_last_apply_result_after_canvas_apply(
    prev: dict[str, Any] | None,
    graph: Any,
    *,
    supplement_summary: str = "",
) -> dict[str, Any]:
    """
    Rebuild last_apply_result after the GUI applies the workflow graph to the canvas.

    The chat may inject todo_list tasks (import review, code-block review) after the assistant
    workflow returns; ApplyEdits' last_apply_result then describes a graph *without* those tasks.
    Refreshing keeps inject_turn_state / inject_last_edit_block and graph_after aligned with
    graph_ref for the post-apply follow-up run (e.g. mark_completed on the injected task id).
    """
    from core.graph.summary import graph_summary

    prev = prev or {}
    g_dict: dict[str, Any]
    if graph is not None and hasattr(graph, "model_dump"):
        g_dict = graph.model_dump(by_alias=True)
    elif isinstance(graph, dict):
        g_dict = graph
    else:
        g_dict = {"units": [], "connections": []}

    base = (prev.get("edits_summary") or "").strip()
    sup = (supplement_summary or "").strip()
    if sup:
        edits_summary = f"{base}; {sup}" if base else sup
    else:
        edits_summary = base or "applied"

    return {
        "attempted": True,
        "success": True,
        "error": None,
        "edits_summary": edits_summary,
        "graph_after": graph_summary(g_dict),
    }


def build_assistant_workflow_initial_inputs(
    user_message: str,
    graph: Any,
    last_apply_result: dict[str, Any] | None,
    recent_changes: str | None,
    follow_up_context: str = "",
    runtime: str = "native",
    coding_is_allowed: bool = True,
    previous_turn: str = "",
    language_hint: str | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Build initial_inputs for run_workflow(assistant_workflow.json).
    Graph can be dict or ProcessGraph (will be normalized to dict).
    recent_changes: optional diff text from previous run (e.g. get_recent_changes()).
    follow_up_context: optional injected context for follow-up runs (file content, RAG, web, browse, code blocks).
    runtime: "native" | "external" — used to set inject_add_environment_edit, inject_add_code_block_edit, inject_run_workflow, inject_ai_training_integration, inject_running_flow_line, inject_debugging_line, inject_coding_line (line or ""). Caller should derive from the graph via core.normalizer.runtime_detector.is_canonical_runtime(graph) → "native" if True else "external".
    coding_is_allowed: when true and runtime is native, inject_add_code_block_edit and inject_coding_line get the line; else "".
    previous_turn: optional formatted last user+assistant turn (including any RAG/search context) so the model has one prior turn in context.
    language_hint: optional display string for prompts (e.g. \"German (de)\"); if None, detected from user_message via lingua.
    """
    # Keep a handle to the live schema instance; model_dump() can drop or distort nested metadata
    # (e.g. todo_list.tasks) in edge cases, which breaks mark_completed in ApplyEdits (empty list).
    graph_live = graph
    if graph is not None and hasattr(graph, "model_dump"):
        graph = graph.model_dump(by_alias=True)
    if graph is None or not isinstance(graph, dict):
        graph = {"units": [], "connections": []}
    user_message = (user_message or "").strip() or "(No message provided.)"
    if language_hint is None:
        _, language_hint = detect_language_for_prompt(user_message)
    lang = (language_hint or "English (en)").strip() or "English (en)"
    turn_state = _build_turn_state_string(last_apply_result)
    recent_changes_block = (
        (WORKFLOW_DESIGNER_RECENT_CHANGES_PREFIX + (recent_changes or "") + "\n" + WORKFLOW_DESIGNER_DO_NOT_REPEAT)
        if (recent_changes or "").strip()
        else ""
    )
    last_edit_block = _build_last_edit_block_string(last_apply_result, language=lang)
    out: dict[str, dict[str, Any]] = {
        "inject_user_message": {"data": user_message},
        "inject_graph": {"data": graph},
        "inject_turn_state": {"data": turn_state},
        "inject_recent_changes_block": {"data": recent_changes_block},
        "inject_last_edit_block": {"data": last_edit_block},
    }
    out["inject_follow_up_context"] = {"data": (follow_up_context or "").strip()}
    out["inject_previous_turn"] = {"data": (previous_turn or "").strip()}
    # Conditional prompt lines: inject per key (runtime/coding_is_allowed in handler)
    r = (runtime or "native").strip()
    out["inject_add_environment_edit"] = {"data": WORKFLOW_DESIGNER_ADD_ENVIRONMENT_LINE.strip() if r == "native" else ""}
    out["inject_add_code_block_edit"] = {"data": WORKFLOW_DESIGNER_ADD_CODE_BLOCK_LINE.strip() if (r == "native" and coding_is_allowed) else ""}
    out["inject_run_workflow"] = {"data": WORKFLOW_DESIGNER_RUN_WORKFLOW_LINE.strip() if r == "native" else ""}
    out["inject_ai_training_integration"] = {"data": WORKFLOW_DESIGNER_AI_TRAINING_NATIVE.strip() if r == "native" else (WORKFLOW_DESIGNER_AI_TRAINING_EXTERNAL.strip() if r == "external" else "")}
    out["inject_running_flow_line"] = {"data": WORKFLOW_DESIGNER_RUNNING_FLOW_LINE.strip() if r == "native" else ""}
    out["inject_debugging_line"] = {"data": WORKFLOW_DESIGNER_DEBUGGING_LINE.strip() if r == "native" else ""}
    out["inject_coding_line"] = {"data": WORKFLOW_DESIGNER_CODING_LINE.strip() if (r == "native" and coding_is_allowed) else ""}
    # Ensure inject_graph carries the same todo_list as the canvas ProcessGraph (source of truth).
    inject_data = out["inject_graph"].get("data")
    if isinstance(inject_data, dict) and graph_live is not None:
        tl_live = getattr(graph_live, "todo_list", None)
        if tl_live is not None and hasattr(tl_live, "model_dump"):
            inject_data["todo_list"] = tl_live.model_dump(by_alias=True)
        elif tl_live is not None and isinstance(tl_live, dict):
            inject_data["todo_list"] = dict(tl_live)
    return out


def build_self_correction_retry_inputs(
    failed_apply_result: dict[str, Any],
    graph: Any,
    recent_changes: str | None,
    runtime: str = "native",
    coding_is_allowed: bool = True,
    previous_turn: str = "",
    language_hint: str | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Build initial_inputs for a same-turn self-correction retry when apply failed.
    Uses WORKFLOW_DESIGNER_RETRY_USER as the user message and failed_apply_result so
    inject_last_edit_block contains the error and self-correction instructions.
    Caller (chat) runs the workflow with these inputs and then applies the result or shows toast.
    previous_turn: optional prior user+assistant summary (same as main workflow) so the model keeps context.
    """
    err_str = str(failed_apply_result.get("error", "Unknown"))[:500]
    if language_hint is None:
        _, language_hint = detect_language_for_prompt("")
    lang = (language_hint or "English (en)").strip() or "English (en)"
    retry_user_message = WORKFLOW_DESIGNER_RETRY_USER.format(error=err_str, language=lang)
    return build_assistant_workflow_initial_inputs(
        retry_user_message,
        graph,
        failed_apply_result,
        recent_changes,
        follow_up_context="",
        runtime=runtime,
        coding_is_allowed=coding_is_allowed,
        previous_turn=(previous_turn or "").strip(),
        language_hint=lang,
    )


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
            CREATE_FILENAME_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            unit_param_overrides=overrides,
            format="dict",
            execution_timeout_s=execution_timeout_s,
        )
        action = (outputs.get("llm_agent") or {}).get("action")
        return (action or "").strip() if isinstance(action, str) else ""
    except Exception:
        return ""


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
    execution_timeout_s: float | None = DEFAULT_EXECUTION_TIMEOUT_S,
    stream_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Run rl_coach_workflow.json and return reply for the GUI.
    Returns dict with keys: reply (str), workflow_errors (list of (unit_id, message)).
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


def build_assistant_workflow_unit_param_overrides(
    provider: str,
    cfg: dict[str, Any],
    rag_persist_dir: str,
    rag_embedding_model: str,
    report_output_dir: str | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Build unit_param_overrides for run_workflow(assistant_workflow.json) from app_settings.json.
    Workflow JSON may use "{settings}" as a placeholder for these params; the GUI/chat injects
    the actual values here: llm_agent (model_name, provider, host), rag_search
    (persist_dir, embedding_model), prompt_llm (template_path), report (output_dir).
    """
    model_name = (cfg.get("model") or "").strip() or "llama3.2"
    host = (cfg.get("host") or "http://127.0.0.1:11434").strip()
    overrides: dict[str, dict[str, Any]] = {
        "llm_agent": {
            "model_name": model_name,
            "provider": (provider or "ollama").strip(),
            "host": host,
        },
        "rag_search": {
            "persist_dir": rag_persist_dir,
            "embedding_model": rag_embedding_model,
        },
        "prompt_llm": {
            "template_path": str(get_workflow_designer_prompt_path()),
        },
    }
    if report_output_dir:
        overrides["report"] = {"output_dir": report_output_dir}
    return overrides


def run_assistant_workflow(
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    execution_timeout_s: float | None = DEFAULT_EXECUTION_TIMEOUT_S,
    stream_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Run assistant_workflow.json and return merge_response.data for the GUI.
    Returns dict with keys: reply, result, status, graph, diff, parser_output, run_output.
    Raises WorkflowTimeoutError if execution exceeds execution_timeout_s (timeout then drop).
    Registers data_bi units (Filter) so the workflow's rag_filter unit is available.
    stream_callback: optional; each LLM token chunk is passed here (called from executor thread).
    """
    try:
        from units.data_bi import register_data_bi_units
        register_data_bi_units()
    except Exception:
        pass
    outputs = run_workflow(
        ASSISTANT_WORKFLOW_PATH,
        initial_inputs=initial_inputs,
        unit_param_overrides=unit_param_overrides,
        format="dict",
        execution_timeout_s=execution_timeout_s,
        stream_callback=stream_callback,
    )
    data = (outputs.get("merge_response") or {}).get("data")
    # Build return shape; if merge_response.data is missing or not a dict, still try to show LLM reply from llm_agent
    if not isinstance(data, dict):
        data = {"reply": "", "result": {}, "status": {}, "graph": None, "diff": "", "parser_output": None, "run_output": {}, "report_output": {}, "grep_output": {}}
    if "parser_output" not in data:
        data = {**data, "parser_output": None}
    if "run_output" not in data:
        data = {**data, "run_output": {}}
    if "report_output" not in data:
        data = {**data, "report_output": {}}
    if "grep_output" not in data:
        data = {**data, "grep_output": {}}
    # Fallback: if merge_response didn't get reply (e.g. connection order / missing data), use llm_agent.action so chat always shows the response
    reply_val = data.get("reply")
    if not (isinstance(reply_val, str) and reply_val.strip()):
        llm_out = (outputs.get("llm_agent") or {})
        if isinstance(llm_out.get("action"), str) and llm_out["action"].strip():
            data = {**data, "reply": llm_out["action"].strip()}
    data["workflow_errors"] = collect_workflow_errors(outputs)
    return data


def run_current_graph(
    graph: ProcessGraph | dict[str, Any] | None,
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    stream_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Run the given graph in memory (no file). Same contract as run_assistant_workflow:
    returns merge_response.data shape (reply, result, status, ...) for GUI.
    Use in -dev mode to run the current designer graph with the chat message.
    stream_callback: optional; each LLM token chunk is passed here (called from executor thread).
    """
    if graph is None:
        return {"reply": "", "result": {}, "status": {}, "graph": None, "diff": "", "parser_output": None, "run_output": {}, "report_output": {}, "grep_output": {}, "workflow_errors": [("run_current_graph", "No graph loaded.")]}
    try:
        from units.data_bi import register_data_bi_units
        register_data_bi_units()
    except Exception:
        pass
    from units.register_env_agnostic import register_env_agnostic_units
    register_env_agnostic_units()
    try:
        from units.canonical import register_canonical_units
        register_canonical_units()
    except Exception:
        pass

    if isinstance(graph, ProcessGraph):
        pg = graph
    else:
        g_dict = graph if isinstance(graph, dict) else (graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else None)
        if g_dict is None:
            return {"reply": "", "result": {}, "status": {}, "graph": None, "diff": "", "parser_output": None, "run_output": {}, "report_output": {}, "grep_output": {}, "workflow_errors": [("run_current_graph", "Graph must be dict or ProcessGraph.")]}
        g_norm, norm_err = run_normalize_graph(g_dict, format="dict")
        if norm_err or g_norm is None:
            return {"reply": "", "result": {}, "status": {}, "graph": None, "diff": "", "parser_output": None, "run_output": {}, "report_output": {}, "grep_output": {}, "workflow_errors": [("run_current_graph", norm_err or "Normalize failed")]}
        pg = ProcessGraph.model_validate(g_norm)

    if unit_param_overrides:
        new_units = []
        for u in pg.units:
            over = unit_param_overrides.get(u.id)
            if over and isinstance(over, dict):
                new_units.append(u.model_copy(update={"params": {**(u.params or {}), **over}}))
            else:
                new_units.append(u)
        pg = pg.model_copy(update={"units": new_units})

    # Re-register canonical so Aggregate/Prompt have step_fn (normalized graph may have loaded n8n and overwritten).
    try:
        from units.canonical import register_canonical_units
        register_canonical_units()
    except Exception:
        pass
    executor = GraphExecutor(pg)
    outputs = executor.execute(
        initial_inputs=initial_inputs or {},
        stream_callback=stream_callback,
    )

    data = (outputs.get("merge_response") or {}).get("data")
    if not isinstance(data, dict):
        data = {"reply": "", "result": {}, "status": {}, "graph": None, "diff": "", "parser_output": None, "run_output": {}, "report_output": {}, "grep_output": {}}
    if "parser_output" not in data:
        data = {**data, "parser_output": None}
    if "run_output" not in data:
        data = {**data, "run_output": {}}
    if "report_output" not in data:
        data = {**data, "report_output": {}}
    if "grep_output" not in data:
        data = {**data, "grep_output": {}}
    # Fallback: if merge_response didn't get reply, use llm_agent.action so chat always shows the response
    reply_val = data.get("reply")
    if not (isinstance(reply_val, str) and reply_val.strip()):
        llm_out = (outputs.get("llm_agent") or {})
        if isinstance(llm_out.get("action"), str) and llm_out["action"].strip():
            data = {**data, "reply": llm_out["action"].strip()}
    data["workflow_errors"] = collect_workflow_errors(outputs)
    return data
