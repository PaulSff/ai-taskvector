"""
Workflow Designer assistant handler: build initial_inputs and run assistant_workflow.json.

Chat runs the workflow via run_assistant_workflow(); prompt and response handling live in the workflow.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from assistants.prompts import (
    WORKFLOW_DESIGNER_DO_NOT_REPEAT,
    WORKFLOW_DESIGNER_RECENT_CHANGES_PREFIX,
    WORKFLOW_DESIGNER_SELF_CORRECTION,
    WORKFLOW_DESIGNER_TURN_STATE_PREFIX,
)
from runtime.run import run_workflow

try:
    from gui.flet.components.settings import (
        get_assistant_workflow_path,
        get_browser_workflow_path,
        get_web_search_workflow_path,
        get_workflow_designer_prompt_path,
    )
except ImportError:
    _FALLBACK_ROOT = Path(__file__).resolve().parent.parent.parent.parent
    _FALLBACK_DIR = _FALLBACK_ROOT / "assistants"
    def get_assistant_workflow_path():
        return _FALLBACK_DIR / "assistant_workflow.json"
    def get_web_search_workflow_path():
        return _FALLBACK_DIR / "web_search.json"
    def get_browser_workflow_path():
        return _FALLBACK_DIR / "browser.json"
    def get_workflow_designer_prompt_path():
        return _FALLBACK_ROOT / "config" / "prompts" / "workflow_designer.json"

# Resolve paths from app settings (relative to repo root)
ASSISTANT_WORKFLOW_PATH = get_assistant_workflow_path()
WEB_SEARCH_WORKFLOW_PATH = get_web_search_workflow_path()
BROWSER_WORKFLOW_PATH = get_browser_workflow_path()


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
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """
    Run a workflow and return (outputs, errors). Error collection is done here so
    callers (e.g. chat) only need to display errors (toast), not import collect_workflow_errors.
    """
    outputs = run_workflow(
        path,
        initial_inputs=initial_inputs or {},
        unit_param_overrides=unit_param_overrides,
        format=format,
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
) -> str:
    """Build the last-edit paragraph for inject_last_edit_block (failed/applied or empty)."""
    if last_apply_result is None:
        return ""
    if last_apply_result.get("success") is False:
        error_msg = last_apply_result.get("error") or "Unknown error"
        return "Last edit failed. " + self_correction_template.format(error=error_msg) + "\n" + WORKFLOW_DESIGNER_DO_NOT_REPEAT
    summary = last_apply_result.get("edits_summary") or ""
    if summary:
        return "Last edit applied successfully. Applied: " + summary + "\n" + WORKFLOW_DESIGNER_DO_NOT_REPEAT
    return "Last edit applied successfully.\n" + WORKFLOW_DESIGNER_DO_NOT_REPEAT


def build_assistant_workflow_initial_inputs(
    user_message: str,
    graph: Any,
    last_apply_result: dict[str, Any] | None,
    recent_changes: str | None,
    follow_up_context: str = "",
) -> dict[str, dict[str, Any]]:
    """
    Build initial_inputs for run_workflow(assistant_workflow.json).
    Graph can be dict or ProcessGraph (will be normalized to dict).
    recent_changes: optional diff text from previous run (e.g. get_recent_changes()).
    follow_up_context: optional injected context for follow-up runs (file content, RAG, web, browse, code blocks).
    """
    if graph is not None and hasattr(graph, "model_dump"):
        graph = graph.model_dump(by_alias=True)
    if graph is None or not isinstance(graph, dict):
        graph = {"units": [], "connections": []}
    turn_state = _build_turn_state_string(last_apply_result)
    recent_changes_block = (
        (WORKFLOW_DESIGNER_RECENT_CHANGES_PREFIX + (recent_changes or "") + "\n" + WORKFLOW_DESIGNER_DO_NOT_REPEAT)
        if (recent_changes or "").strip()
        else ""
    )
    last_edit_block = _build_last_edit_block_string(last_apply_result)
    out: dict[str, dict[str, Any]] = {
        "inject_user_message": {"data": user_message},
        "inject_graph": {"data": graph},
        "inject_turn_state": {"data": turn_state},
        "inject_recent_changes_block": {"data": recent_changes_block},
        "inject_last_edit_block": {"data": last_edit_block},
    }
    out["inject_follow_up_context"] = {"data": (follow_up_context or "").strip()}
    return out


def build_assistant_workflow_unit_param_overrides(
    provider: str,
    cfg: dict[str, Any],
    rag_persist_dir: str,
    rag_embedding_model: str,
) -> dict[str, dict[str, Any]]:
    """
    Build unit_param_overrides for run_workflow(assistant_workflow.json):
    llm_agent (model_name, provider, host), rag_search/rag_search_action (persist_dir, embedding_model),
    prompt_llm (template_path from app settings).
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
        "rag_search_action": {
            "persist_dir": rag_persist_dir,
            "embedding_model": rag_embedding_model,
        },
        "prompt_llm": {
            "template_path": str(get_workflow_designer_prompt_path()),
        },
    }
    return overrides


def run_assistant_workflow(
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Run assistant_workflow.json and return merge_response.data for the GUI.
    Returns dict with keys: reply, result, status, graph, diff, parser_output, run_output.
    Raises or returns partial dict on workflow/unit errors; caller should handle missing keys.
    Registers data_bi units (Filter) so the workflow's rag_filter unit is available.
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
    )
    data = (outputs.get("merge_response") or {}).get("data")
    if not isinstance(data, dict):
        return {"reply": "", "result": {}, "status": {}, "graph": None, "diff": "", "parser_output": None, "run_output": {}, "workflow_errors": collect_workflow_errors(outputs)}
    if "parser_output" not in data:
        data = {**data, "parser_output": None}
    if "run_output" not in data:
        data = {**data, "run_output": {}}
    data["workflow_errors"] = collect_workflow_errors(outputs)
    return data
