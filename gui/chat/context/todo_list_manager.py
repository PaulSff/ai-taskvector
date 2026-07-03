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
  if missing, then run a second agent turn to describe the imported graph and mark_completed.
- add_unit (any type, chat post-apply): add two open tasks with the new unit id(s) in one line each:
  "Ensure the units are connected properly: {ids}." and "Check and adjust the units params: {ids}."
- run_workflow (chat follow-up): ensure two open tasks exist:
  "Make sure to have a Debug unit in place and wired into the flow. Set the path for the log file in params to grep the logs from there."
  and "Prepare initial data for the workflow to test with."

- Before adding either task, we check if an open (non-completed) task with the same text already
  exists; if so, we skip adding to avoid duplicates when the agent repeats read_code_block or
  add_unit for the same unit.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional, Sequence

# publish/await runtime
from runtime import (
    ZmqPublisher,
    ZmqSubscriber,
    ZmqSubscriptionConfig,
    ZmqTopics,
)
from runtime.run import WorkflowTimeoutError

# ---- slot allocator (configure N >= max concurrent calls) ----
N = 10

_JOB_PUB_ENDPOINTS = [f"tcp://127.0.0.1:{6221 + 2 * i}" for i in range(N)]
_RESPONSE_ENDPOINTS = [f"tcp://127.0.0.1:{6231 + 2 * i}" for i in range(N)]
_RESPONSE_SUB_ENDPOINTS = _RESPONSE_ENDPOINTS

_slot_sem = asyncio.Semaphore(N)
_slot_next = 0
_slot_lock = asyncio.Lock()


async def _acquire_slot() -> int:
    global _slot_next
    await _slot_sem.acquire()
    async with _slot_lock:
        slot = _slot_next
        _slot_next = (_slot_next + 1) % N
    return slot


async def _release_slot() -> None:
    _slot_sem.release()


FormatProcess = str  # "dict","yaml","pyflow" if needed


async def _publish_and_wait(
    path: Path,
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    *,
    format: FormatProcess = "dict",
    execution_timeout_s: float | None = None,
) -> dict[str, Any]:
    """
    Publish workflow to the workflow server and await results.
    GUI never runs workflows directly.
    """
    slot = await _acquire_slot()
    try:
        import time
        import uuid

        run_id = uuid.uuid4().hex
        wp = path.resolve()

        job_pub = ZmqPublisher(
            pub_endpoint=_JOB_PUB_ENDPOINTS[slot],
            topics=ZmqTopics(),
        )

        resp_endpoint = _RESPONSE_ENDPOINTS[slot]

        topics = ZmqTopics()
        sub = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=_RESPONSE_SUB_ENDPOINTS[slot],
                topics=(topics.token, topics.result, topics.error),
                accept_topics=None,
                rcvtimeo_ms=200,
            )
        )

        final_outputs: Optional[dict[str, Any]] = None
        has_workflow_error = False
        workflow_error = ""

        async def _on_error(_topic: str, payload: dict[str, Any]) -> None:
            nonlocal has_workflow_error, workflow_error
            if payload.get("run_id") != run_id:
                return
            err = payload.get("error")
            workflow_error = err if isinstance(err, str) else str(err)
            has_workflow_error = True

        async def _on_result(_topic: str, payload: dict[str, Any]) -> None:
            nonlocal final_outputs
            if payload.get("run_id") != run_id:
                return
            outs = payload.get("outputs")
            final_outputs = outs if isinstance(outs, dict) else {}

        async def _on_token(_topic: str, _payload: dict[str, Any]) -> None:
            return

        sub.on(topics.token, _on_token)
        sub.on(topics.result, _on_result)
        sub.on(topics.error, _on_error)

        await asyncio.wait_for(sub.start(), timeout=30)

        try:
            job_pub.publish_job(
                run_id=run_id,
                workflow_path=str(wp),
                initial_inputs=initial_inputs,
                unit_param_overrides=unit_param_overrides or {},
                format=format,
                response_endpoint=resp_endpoint,
            )

            start = time.monotonic()
            while final_outputs is None and not has_workflow_error:
                if (
                    execution_timeout_s is not None
                    and (time.monotonic() - start) > execution_timeout_s
                ):
                    raise WorkflowTimeoutError(execution_timeout_s)
                await asyncio.sleep(0.01)
        finally:
            await sub.stop()

        if has_workflow_error:
            raise RuntimeError(workflow_error)

        return final_outputs or {}
    finally:
        await _release_slot()


# ---- todo manager logic (same semantics, refactored to await publishes) ----

TASK_PREFIX_REVIEW_SOURCE = "Review the source "
TASK_PREFIX_ADD_CODE_BLOCK = "Add the code block to "

TASK_REVIEW_IMPORTED_WORKFLOW = "Review the workflow"

TASK_ENSURE_UNITS_CONNECTED = (
    "Verify the units connections and ports: {unit_ids}. "
    "Ensure the ports types compatibility (e.g. 'tables' -> 'tables') to pass the data in correct format."
)
TASK_CHECK_UNITS_PARAMS = (
    "Search the units params description on the knowledge base, unless it is a custom function: {unit_ids}. "
    "Trace data keys all the way through the flow and adjust the units params to meet the specificaton."
)
TASK_ENSURE_DEBUG_FOR_RUN = (
    "Ensure to have a Debug unit in place to collect both output Data and Errors from units (typically at the tail of the workflow). "
    "Set a log file path in the Debug unit params to grep the logs from there. "
)
TASK_PREPARE_INITIAL_DATA_FOR_RUN = (
    "Ensure the to have a Template unit with some input data in params for the workflow to test with. "
    "Test the workflow, put a comment summarizing the testing result on the graph."
)


def _default_todo_list_workflow_path() -> Path:
    """Resolve todo_list.json via agents/tools/todo_manager/tool.yaml (shared with the edit runner)."""
    try:
        from agents.tools.workflow_path import get_tool_workflow_path

        return get_tool_workflow_path("todo_manager")
    except Exception:
        repo = Path(__file__).resolve().parents[3]
        return repo / "agents" / "tools" / "todo_manager" / "todo_list.json"


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


async def _run_todo_list_workflow_publish(
    graph: dict[str, Any],
    todo_params: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    """
    Publish todo_manager workflow to server and return updated graph.
    """

    path = workflow_path or _default_todo_list_workflow_path()
    if not path.is_file():
        return graph

    initial_inputs = {"inject_graph": {"data": graph}}
    unit_param_overrides = {"todo_list": todo_params}

    try:
        out = await _publish_and_wait(
            path,
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format="dict",
        )
        out_graph = (out.get("todo_list") or {}).get("graph")
        if isinstance(out_graph, dict):
            return out_graph
    except Exception:
        pass
    return graph


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


async def add_tasks_for_read_code_block(
    unit_ids: list[str],
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    if not unit_ids:
        return graph

    current = graph
    todo = current.get("todo_list")
    if not isinstance(todo, dict) or not isinstance(todo.get("tasks"), list):
        current = await _run_todo_list_workflow_publish(
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
        current = await _run_todo_list_workflow_publish(
            current,
            {"action": "add_task", "text": task_text},
            workflow_path,
        )

    return current


async def add_task_for_add_code_block(
    unit_id: str,
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    if not (unit_id or "").strip():
        return graph
    unit_id = str(unit_id).strip()

    current = graph
    todo = current.get("todo_list")
    if not isinstance(todo, dict) or not isinstance(todo.get("tasks"), list):
        current = await _run_todo_list_workflow_publish(
            current,
            {"action": "add_todo_list", "title": "Workflow Designer"},
            workflow_path,
        )

    task_text = TASK_PREFIX_ADD_CODE_BLOCK + unit_id
    if _has_open_task_with_text(current, task_text):
        return current

    return await _run_todo_list_workflow_publish(
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

    current = graph
    todo = current.get("todo_list")
    if not isinstance(todo, dict) or not isinstance(todo.get("tasks"), list):
        current = await _run_todo_list_workflow_publish(
            current,
            {"action": "add_todo_list", "title": "Workflow Designer"},
            workflow_path,
        )

    if not _has_open_task_with_text(current, text_connected):
        current = await _run_todo_list_workflow_publish(
            current,
            {"action": "add_task", "text": text_connected},
            workflow_path,
        )

    if not _has_open_task_with_text(current, text_params):
        current = await _run_todo_list_workflow_publish(
            current,
            {"action": "add_task", "text": text_params},
            workflow_path,
        )

    return current


async def add_tasks_for_run_workflow(
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    if not graph or not isinstance(graph, dict):
        return graph

    current = graph
    todo = current.get("todo_list")
    if not isinstance(todo, dict) or not isinstance(todo.get("tasks"), list):
        current = await _run_todo_list_workflow_publish(
            current,
            {"action": "add_todo_list", "title": "Workflow Designer"},
            workflow_path,
        )

    if not _has_open_task_with_text(current, TASK_ENSURE_DEBUG_FOR_RUN):
        current = await _run_todo_list_workflow_publish(
            current,
            {"action": "add_task", "text": TASK_ENSURE_DEBUG_FOR_RUN},
            workflow_path,
        )

    if not _has_open_task_with_text(current, TASK_PREPARE_INITIAL_DATA_FOR_RUN):
        current = await _run_todo_list_workflow_publish(
            current,
            {"action": "add_task", "text": TASK_PREPARE_INITIAL_DATA_FOR_RUN},
            workflow_path,
        )

    return current


async def add_review_workflow_task_after_import(
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    if not graph or not isinstance(graph, dict):
        return graph

    current = graph
    todo = current.get("todo_list")
    if not isinstance(todo, dict) or not isinstance(todo.get("tasks"), list):
        current = await _run_todo_list_workflow_publish(
            current,
            {"action": "add_todo_list", "title": "Workflow Designer"},
            workflow_path,
        )

    if _has_open_task_with_text(current, TASK_REVIEW_IMPORTED_WORKFLOW):
        return current

    return await _run_todo_list_workflow_publish(
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
    added_unit_ids: list[str] = []

    for e in edits or []:
        if isinstance(e, dict) and e.get("action") == "add_unit":
            u = e.get("unit") or {}
            uid = (u.get("id") or "").strip()
            if uid:
                added_unit_ids.append(uid)

    if added_unit_ids:
        current = await add_tasks_for_added_units(
            added_unit_ids, current, workflow_path
        )
        supplements.append("client: todo tasks for add_unit (connections + params)")

    if any(
        isinstance(e, dict) and e.get("action") == "run_workflow" for e in (edits or [])
    ):
        current = await add_tasks_for_run_workflow(current, workflow_path)
        supplements.append("client: todo tasks for run_workflow (debug + initial data)")

    if coding_is_allowed:
        for e in edits or []:
            if isinstance(e, dict) and e.get("action") == "add_unit":
                u = e.get("unit") or {}
                if str(u.get("type", "")).strip().lower() in ("function", "script"):
                    uid = (u.get("id") or "").strip()
                    if uid:
                        current = await add_task_for_add_code_block(
                            uid, current, workflow_path
                        )
                        supplements.append("client: todo task for code block unit")

    if any(
        isinstance(e, dict) and e.get("action") == "import_workflow"
        for e in (edits or [])
    ):
        current = await add_review_workflow_task_after_import(current, workflow_path)
        supplements.append('client: todo task "Review the workflow"')

    return current, supplements
