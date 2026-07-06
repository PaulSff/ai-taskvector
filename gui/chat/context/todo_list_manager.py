from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Sequence

DEFAULT_TODO_LIST_TITLE = "Current flow TODOs"
TASK_PREFIX_REVIEW_SOURCE = "Review the source "
TASK_PREFIX_ADD_CODE_BLOCK = "Add the code block to "

TASK_REVIEW_IMPORTED_WORKFLOW = "Review the workflow"

TASK_ENSURE_UNITS_CONNECTED = "Verify the units connections and ports: {unit_ids}. Ensure the ports types compatibility (e.g. 'tables' -> 'tables') to pass the data in correct format."
TASK_CHECK_UNITS_PARAMS = "Search the units params description on the knowledge base, unless it is a custom function: {unit_ids}. Trace data keys all the way through the flow and adjust the units params to meet the specificaton."
TASK_ENSURE_DEBUG_FOR_RUN = (
    "Ensure to have a Debug unit in place to collect both output Data and Errors from units (typically at the tail of the workflow). "
    "Set a log file path in the Debug unit params to grep the logs from there. "
)
TASK_PREPARE_INITIAL_DATA_FOR_RUN = "Ensure the to have a Template unit with some input data in params for the workflow to test with. Test the workflow, put a comment summarizing the testing result on the graph."

TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE = "Reply to the incoming message: "


def _default_todo_list_workflow_path() -> Path:
    from agents.tools.workflow_path import get_tool_workflow_path

    return get_tool_workflow_path("todo_manager")


def _has_open_task_with_text(graph: dict[str, Any], task_text: str) -> bool:
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
    include_code_block_source = bool(coding_is_allowed)
    include_source_for_unit_ids: list[str] | None = None
    if not coding_is_allowed:
        include_source_for_unit_ids = get_unit_ids_with_source_tasks(graph)
    return {
        "include_code_block_source": include_code_block_source,
        "include_source_for_unit_ids": include_source_for_unit_ids or [],
    }


def _run_todo_list_workflow_sync(
    graph: dict[str, Any],
    todo_params: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
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


async def _run_todo_list_workflow(
    graph: dict[str, Any],
    todo_params: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _run_todo_list_workflow_sync, graph, todo_params, workflow_path
    )


def _as_todo_params_sequential(edits: list[dict[str, Any]]) -> dict[str, Any]:
    # If more than one edit, use the batch input shape; otherwise keep it single-edit.
    if len(edits) == 1:
        return edits[0]
    return {"Multiple_edits_sequential": edits}


async def _ensure_todo_list_exists(
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    current = graph
    todo = current.get("todo_list")
    if not isinstance(todo, dict) or not isinstance(todo.get("tasks"), list):
        current = await _run_todo_list_workflow(
            current,
            {"action": "add_todo_list", "title": DEFAULT_TODO_LIST_TITLE},
            workflow_path,
        )
    return current


async def add_tasks_for_read_code_block(
    unit_ids: list[str],
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    if not unit_ids:
        return graph

    current = await _ensure_todo_list_exists(graph, workflow_path)

    edits: list[dict[str, Any]] = []
    for uid in unit_ids:
        uid = (uid or "").strip()
        if not uid:
            continue
        task_text = TASK_PREFIX_REVIEW_SOURCE + uid
        if _has_open_task_with_text(current, task_text):
            continue
        edits.append({"action": "add_task", "text": task_text})

    if not edits:
        return current

    return await _run_todo_list_workflow(
        current,
        _as_todo_params_sequential(edits),
        workflow_path,
    )


async def add_task_for_add_code_block(
    unit_id: str,
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    if not (unit_id or "").strip():
        return graph
    unit_id = str(unit_id).strip()

    current = await _ensure_todo_list_exists(graph, workflow_path)

    task_text = TASK_PREFIX_ADD_CODE_BLOCK + unit_id
    if _has_open_task_with_text(current, task_text):
        return current

    return await _run_todo_list_workflow(
        current,
        {"action": "add_task", "text": task_text},
        workflow_path,
    )


async def add_tasks_for_added_units(
    unit_ids: list[str],
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
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

    current = await _ensure_todo_list_exists(graph, workflow_path)

    edits: list[dict[str, Any]] = []
    if not _has_open_task_with_text(current, text_connected):
        edits.append({"action": "add_task", "text": text_connected})
    if not _has_open_task_with_text(current, text_params):
        edits.append({"action": "add_task", "text": text_params})

    if not edits:
        return current

    return await _run_todo_list_workflow(
        current,
        _as_todo_params_sequential(edits),
        workflow_path,
    )


async def add_tasks_for_run_workflow(
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    if not graph or not isinstance(graph, dict):
        return graph

    current = await _ensure_todo_list_exists(graph, workflow_path)

    edits: list[dict[str, Any]] = []
    if not _has_open_task_with_text(current, TASK_ENSURE_DEBUG_FOR_RUN):
        edits.append({"action": "add_task", "text": TASK_ENSURE_DEBUG_FOR_RUN})
    if not _has_open_task_with_text(current, TASK_PREPARE_INITIAL_DATA_FOR_RUN):
        edits.append({"action": "add_task", "text": TASK_PREPARE_INITIAL_DATA_FOR_RUN})

    if not edits:
        return current

    return await _run_todo_list_workflow(
        current,
        _as_todo_params_sequential(edits),
        workflow_path,
    )


async def add_review_workflow_task_after_import(
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    if not graph or not isinstance(graph, dict):
        return graph

    current = await _ensure_todo_list_exists(graph, workflow_path)

    if _has_open_task_with_text(current, TASK_REVIEW_IMPORTED_WORKFLOW):
        return current

    return await _run_todo_list_workflow(
        current,
        {"action": "add_task", "text": TASK_REVIEW_IMPORTED_WORKFLOW},
        workflow_path,
    )


async def augment_graph_with_client_tasks(
    graph: dict[str, Any],
    edits: Sequence[Any] | None,
    *,
    coding_is_allowed: bool,
    workflow_path: Path | None = None,
) -> tuple[dict[str, Any], list[str]]:
    supplements: list[str] = []
    if not graph or not isinstance(graph, dict):
        return graph, supplements

    current = graph

    edits_to_apply: list[dict[str, Any]] = []
    ensured_todo_list = False

    queued_task_texts: set[str] = set()

    def ensure_todo_list_if_missing() -> None:
        nonlocal ensured_todo_list
        if ensured_todo_list:
            return
        todo = current.get("todo_list")
        if isinstance(todo, dict) and isinstance(todo.get("tasks"), list):
            ensured_todo_list = True
            return
        edits_to_apply.append(
            {"action": "add_todo_list", "title": DEFAULT_TODO_LIST_TITLE}
        )
        ensured_todo_list = True

    def queue_add_task(task_text: str) -> None:
        text = (task_text or "").strip()
        if not text:
            return
        if text in queued_task_texts:
            return
        # Check against initial graph state (current is not updated mid-queue).
        if _has_open_task_with_text(current, text):
            return
        queued_task_texts.add(text)
        edits_to_apply.append({"action": "add_task", "text": text})

    # Collect added unit ids
    added_unit_ids: list[str] = []
    for e in edits or []:
        if isinstance(e, dict) and e.get("action") == "add_unit":
            u = e.get("unit") or {}
            uid = (u.get("id") or "").strip()
            if uid:
                added_unit_ids.append(uid)

    # Preserve existing supplement strings (unchanged meaning)
    if added_unit_ids:
        supplements.append("client: todo tasks for add_unit (connections + params)")

    # Order unit ids deterministically and build comma-separated text
    ordered_unit_ids: list[str] = []
    seen_uids: set[str] = set()
    for raw in added_unit_ids:
        uid = (raw or "").strip()
        if uid and uid not in seen_uids:
            seen_uids.add(uid)
            ordered_unit_ids.append(uid)

    # Queue tasks for add_unit
    if ordered_unit_ids:
        unit_ids_str = ", ".join(ordered_unit_ids)
        text_connected = TASK_ENSURE_UNITS_CONNECTED.format(unit_ids=unit_ids_str)
        text_params = TASK_CHECK_UNITS_PARAMS.format(unit_ids=unit_ids_str)

        ensure_todo_list_if_missing()
        queue_add_task(text_connected)
        queue_add_task(text_params)

    # Queue tasks for run_workflow
    if any(
        isinstance(e, dict) and e.get("action") == "run_workflow" for e in (edits or [])
    ):
        supplements.append("client: todo tasks for run_workflow (debug + initial data)")
        ensure_todo_list_if_missing()
        queue_add_task(TASK_ENSURE_DEBUG_FOR_RUN)
        queue_add_task(TASK_PREPARE_INITIAL_DATA_FOR_RUN)

    # Queue tasks for code blocks (one per eligible unit id)
    if coding_is_allowed:
        code_unit_ids: list[str] = []
        for e in edits or []:
            if isinstance(e, dict) and e.get("action") == "add_unit":
                u = e.get("unit") or {}
                if str(u.get("type", "")).strip().lower() in ("function", "script"):
                    uid = (u.get("id") or "").strip()
                    if uid:
                        code_unit_ids.append(uid)

        # Preserve earlier behavior of potentially allowing duplicates, but we'll de-dupe for batching.
        for uid in list(dict.fromkeys(code_unit_ids)):
            ensure_todo_list_if_missing()
            queue_add_task(TASK_PREFIX_ADD_CODE_BLOCK + uid)

        if code_unit_ids:
            supplements.append("client: todo task for code block unit")

    # Queue tasks for import_workflow
    if any(
        isinstance(e, dict) and e.get("action") == "import_workflow"
        for e in (edits or [])
    ):
        supplements.append('client: todo task "Review the workflow"')
        ensure_todo_list_if_missing()
        queue_add_task(TASK_REVIEW_IMPORTED_WORKFLOW)

    if not edits_to_apply:
        return current, supplements

    todo_params: dict[str, Any]
    if len(edits_to_apply) == 1:
        todo_params = edits_to_apply[0]
    else:
        todo_params = {"Multiple_edits_sequential": edits_to_apply}

    updated = await _run_todo_list_workflow(current, todo_params, workflow_path)
    return updated, supplements
