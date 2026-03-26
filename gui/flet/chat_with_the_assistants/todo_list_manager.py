"""
Todo-list manager for Workflow Designer: track tasks by unit_id and control code-block source in graph summary.

- When coding_is_allowed: graph summary includes source for all code blocks.
- When coding is not allowed: source is included only for unit_ids that have an open task
  "Review the source {unit_id}" or "Add the code block to {unit_id}". When the task is completed
  or removed, source for that unit is excluded from the summary.

- read_code_block: add task "Review the source {unit_id}" (and add_todo_list if missing); do not
  inject code into follow-up context — source is shown via summary.
- add_unit (function/script): add task "Add the code block to {unit_id}" (same tracking).
- import_workflow (chat post-apply): ensure todo_list exists and add open task "Review the workflow"
  if missing, then run a second assistant turn to describe the imported graph and mark_completed.
- add_unit (any type, chat post-apply): add two open tasks with the new unit id(s) in one line each:
  "Ensure the units are connected properly: {ids}." and "Check and adjust the units params: {ids}."
- run_workflow (chat follow-up): ensure two open tasks exist:
  "Make sure to have a Debug unit in place and wired into the flow. Set the path for the log file in params to grep the logs from there."
  and "Prepare initial data for the workflow to test with."

- Before adding either task, we check if an open (non-completed) task with the same text already
  exists; if so, we skip adding to avoid duplicates when the assistant repeats read_code_block or
  add_unit for the same unit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from gui.flet.components.settings import get_coding_is_allowed

# Task text prefixes; unit_id is appended or formatted.
TASK_PREFIX_REVIEW_SOURCE = "Review the source "
TASK_PREFIX_ADD_CODE_BLOCK = "Add the code block to "
# After import_workflow apply (Workflow Designer chat): single review task on the TODO list.
TASK_REVIEW_IMPORTED_WORKFLOW = "Review the workflow"

# After add_unit apply (Workflow Designer chat): two tasks per batch of new unit ids (comma-separated).
TASK_ENSURE_UNITS_CONNECTED = "Ensure the units are connected properly: {unit_ids}."
TASK_CHECK_UNITS_PARAMS = "Check and adjust the units params: {unit_ids}."
TASK_ENSURE_DEBUG_FOR_RUN = (
    "Ensure to have a Debug unit in place and wired into the flow. "
    "Set the path for the log file in params to grep the logs from there."
)
TASK_PREPARE_INITIAL_DATA_FOR_RUN = "Verify the initial data for the workflow to test with."


def _default_todo_list_workflow_path() -> Path:
    return Path(__file__).resolve().parent.parent / "components" / "workflow" / "assistants" / "todo_list.json"


def _has_open_task_with_text(graph: dict[str, Any], task_text: str) -> bool:
    """Return True if the graph's todo_list has an open (non-completed) task with exactly this text."""
    if not graph or not isinstance(graph, dict):
        return False
    todo = graph.get("todo_list")
    if not isinstance(todo, dict):
        return False
    tasks = todo.get("tasks")
    if not isinstance(tasks, list):
        return False
    want = (task_text or "").strip()
    if not want:
        return False
    for t in tasks:
        if not isinstance(t, dict) or t.get("completed"):
            continue
        if (t.get("text") or "").strip() == want:
            return True
    return False


def graph_has_any_open_tasks(graph: Any | None) -> bool:
    """True if the graph has a todo_list with at least one task where completed is not true."""
    if graph is None:
        return False
    d = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else graph
    if not isinstance(d, dict):
        return False
    todo = d.get("todo_list")
    if not isinstance(todo, dict):
        return False
    tasks = todo.get("tasks")
    if not isinstance(tasks, list):
        return False
    for t in tasks:
        if isinstance(t, dict) and not t.get("completed"):
            return True
    return False


def get_unit_ids_with_source_tasks(graph: dict[str, Any] | None) -> list[str]:
    """
    Parse the graph's todo_list for tasks that track code-block source by unit_id.
    Returns list of unit_ids that have an open (non-completed) task matching
    "Review the source {unit_id}" or "Add the code block to {unit_id}".
    """
    if not graph or not isinstance(graph, dict):
        return []
    todo = graph.get("todo_list")
    if not isinstance(todo, dict):
        return []
    tasks = todo.get("tasks")
    if not isinstance(tasks, list):
        return []
    unit_ids: list[str] = []
    for t in tasks:
        if not isinstance(t, dict):
            continue
        if t.get("completed"):
            continue
        text = (t.get("text") or "").strip()
        if not text:
            continue
        if text.startswith(TASK_PREFIX_REVIEW_SOURCE):
            uid = text[len(TASK_PREFIX_REVIEW_SOURCE) :].strip()
            if uid:
                unit_ids.append(uid)
        elif text.startswith(TASK_PREFIX_ADD_CODE_BLOCK):
            uid = text[len(TASK_PREFIX_ADD_CODE_BLOCK) :].strip()
            if uid:
                unit_ids.append(uid)
    return list(dict.fromkeys(unit_ids))


def get_summary_params(
    coding_is_allowed: bool,
    graph: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Params for the GraphSummary unit: when to include code-block source in the summary.
    - If coding_is_allowed: include source for all code blocks.
    - Else: include source only for unit_ids that have an open review/add-code task.
    """
    include_code_block_source = bool(coding_is_allowed)
    include_source_for_unit_ids: list[str] | None = None
    if not coding_is_allowed:
        include_source_for_unit_ids = get_unit_ids_with_source_tasks(graph)
    return {
        "include_code_block_source": include_code_block_source,
        "include_source_for_unit_ids": include_source_for_unit_ids or [],
    }


def _run_todo_list_workflow(
    graph: dict[str, Any],
    todo_params: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    """Run todo_list.json with inject_graph and todo_list unit params; return updated graph."""
    from runtime.run import run_workflow

    path = workflow_path or _default_todo_list_workflow_path()
    if not path.is_file():
        return graph
    initial_inputs = {"inject_graph": {"data": graph}}
    unit_param_overrides = {"todo_list": todo_params}
    try:
        outputs = run_workflow(
            path,
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format="dict",
        )
        out_graph = (outputs.get("todo_list") or {}).get("graph")
        if isinstance(out_graph, dict):
            return out_graph
    except Exception:
        pass
    return graph


def add_tasks_for_read_code_block(
    unit_ids: list[str],
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    """
    Ensure todo_list exists (add_todo_list "Workflow Designer" if missing), then add
    task "Review the source {unit_id}" for each unit_id. Returns updated graph.
    """
    if not unit_ids:
        return graph
    current = graph
    todo = current.get("todo_list")
    if not isinstance(todo, dict) or not isinstance(todo.get("tasks"), list):
        current = _run_todo_list_workflow(
            current,
            {"action": "add_todo_list", "title": "Workflow Designer"},
            workflow_path,
        )
    for uid in unit_ids:
        if not uid:
            continue
        task_text = TASK_PREFIX_REVIEW_SOURCE + uid
        if _has_open_task_with_text(current, task_text):
            continue
        current = _run_todo_list_workflow(
            current,
            {"action": "add_task", "text": task_text},
            workflow_path,
        )
    return current


def add_task_for_add_code_block(
    unit_id: str,
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    """
    Add task "Add the code block to {unit_id}". Ensures todo_list exists if needed.
    Returns updated graph.
    """
    if not (unit_id or "").strip():
        return graph
    unit_id = str(unit_id).strip()
    current = graph
    todo = current.get("todo_list")
    if not isinstance(todo, dict) or not isinstance(todo.get("tasks"), list):
        current = _run_todo_list_workflow(
            current,
            {"action": "add_todo_list", "title": "Workflow Designer"},
            workflow_path,
        )
    task_text = TASK_PREFIX_ADD_CODE_BLOCK + unit_id
    if _has_open_task_with_text(current, task_text):
        return current
    return _run_todo_list_workflow(
        current,
        {"action": "add_task", "text": task_text},
        workflow_path,
    )


def add_tasks_for_added_units(
    unit_ids: list[str],
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    """
    After add_unit edits were applied: ensure todo_list exists, then add (if not already open)
    two tasks listing the new unit id(s) as comma-separated text.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in unit_ids:
        uid = (raw or "").strip()
        if not uid or uid in seen:
            continue
        seen.add(uid)
        ordered.append(uid)
    if not ordered or not graph or not isinstance(graph, dict):
        return graph
    unit_ids_str = ", ".join(ordered)
    text_connected = TASK_ENSURE_UNITS_CONNECTED.format(unit_ids=unit_ids_str)
    text_params = TASK_CHECK_UNITS_PARAMS.format(unit_ids=unit_ids_str)
    current = graph
    todo = current.get("todo_list")
    if not isinstance(todo, dict) or not isinstance(todo.get("tasks"), list):
        current = _run_todo_list_workflow(
            current,
            {"action": "add_todo_list", "title": "Workflow Designer"},
            workflow_path,
        )
    if not _has_open_task_with_text(current, text_connected):
        current = _run_todo_list_workflow(
            current,
            {"action": "add_task", "text": text_connected},
            workflow_path,
        )
    if not _has_open_task_with_text(current, text_params):
        current = _run_todo_list_workflow(
            current,
            {"action": "add_task", "text": text_params},
            workflow_path,
        )
    return current


def add_tasks_for_run_workflow(
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    """
    Ensure todo_list exists, then add (if not already open) run-workflow verification tasks:
    - ensure Debug unit wiring/log path
    - prepare initial test data
    """
    if not graph or not isinstance(graph, dict):
        return graph
    current = graph
    todo = current.get("todo_list")
    if not isinstance(todo, dict) or not isinstance(todo.get("tasks"), list):
        current = _run_todo_list_workflow(
            current,
            {"action": "add_todo_list", "title": "Workflow Designer"},
            workflow_path,
        )
    if not _has_open_task_with_text(current, TASK_ENSURE_DEBUG_FOR_RUN):
        current = _run_todo_list_workflow(
            current,
            {"action": "add_task", "text": TASK_ENSURE_DEBUG_FOR_RUN},
            workflow_path,
        )
    if not _has_open_task_with_text(current, TASK_PREPARE_INITIAL_DATA_FOR_RUN):
        current = _run_todo_list_workflow(
            current,
            {"action": "add_task", "text": TASK_PREPARE_INITIAL_DATA_FOR_RUN},
            workflow_path,
        )
    return current


def add_review_workflow_task_after_import(
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    """
    After import_workflow: ensure todo_list exists (title \"Workflow Designer\"), then add task
    \"Review the workflow\" if there is no open task with that text. Returns updated graph dict.
    """
    if not graph or not isinstance(graph, dict):
        return graph
    current = graph
    todo = current.get("todo_list")
    if not isinstance(todo, dict) or not isinstance(todo.get("tasks"), list):
        current = _run_todo_list_workflow(
            current,
            {"action": "add_todo_list", "title": "Workflow Designer"},
            workflow_path,
        )
    if _has_open_task_with_text(current, TASK_REVIEW_IMPORTED_WORKFLOW):
        return current
    return _run_todo_list_workflow(
        current,
        {"action": "add_task", "text": TASK_REVIEW_IMPORTED_WORKFLOW},
        workflow_path,
    )


def augment_graph_with_client_tasks(
    graph: dict[str, Any],
    edits: Sequence[Any] | None,
    *,
    coding_is_allowed: bool,
    workflow_path: Path | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """
    After an applied workflow graph dict is produced, inject client-side todo_list tasks before
    the canvas apply. Returns (updated_graph, supplement_strings for last_apply_result summary).
    """
    supplements: list[str] = []
    if not graph or not isinstance(graph, dict):
        return graph, supplements
    current = graph
    added_unit_ids: list[str] = []
    for e in edits or []:
        if isinstance(e, dict) and e.get("action") == "add_unit":
            u = e.get("unit") or {}
            uid = (u.get("id") or "").strip()
            if uid:
                added_unit_ids.append(uid)
    if added_unit_ids:
        current = add_tasks_for_added_units(added_unit_ids, current, workflow_path)
        supplements.append("client: todo tasks for add_unit (connections + params)")
    if any(
        isinstance(e, dict) and e.get("action") == "run_workflow"
        for e in (edits or [])
    ):
        current = add_tasks_for_run_workflow(current, workflow_path)
        supplements.append("client: todo tasks for run_workflow (debug + initial data)")
    if coding_is_allowed and get_coding_is_allowed():
        for e in edits or []:
            if isinstance(e, dict) and e.get("action") == "add_unit":
                u = e.get("unit") or {}
                if str(u.get("type", "")).strip().lower() in ("function", "script"):
                    uid = (u.get("id") or "").strip()
                    if uid:
                        current = add_task_for_add_code_block(uid, current, workflow_path)
                        supplements.append("client: todo task for code block unit")
    if any(
        isinstance(e, dict) and e.get("action") == "import_workflow"
        for e in (edits or [])
    ):
        current = add_review_workflow_task_after_import(current, workflow_path)
        supplements.append('client: todo task "Review the workflow"')
    return current, supplements
