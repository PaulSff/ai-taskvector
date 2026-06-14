"""
turn_driver (multi-session, thread-safe) is a self-contained module that:

- Manages multiple sessions keyed by session_id (creates one if omitted).
- Runs workflows in threads and streams tokens to an async per-session callback.
- Maintains per-session history, last_apply_result, persistence, and filename suggestion.
- Exposes thread-safe APIs:
  - create_session(session_id: Optional[str]) -> str
  - handle_turn(session_id: Optional[str], user_message: str, messenger: str, *, graph_dict: Optional[dict]=None, role_id: Optional[str]=None, stream_callback: Optional[Callable[[str, str], Coroutine]]=None) -> dict | None
  - stop_run(session_id: str) -> None
  - reset_session(session_id: str) -> None

TODO:
- per-session persistence directories, session GC, or explicit delete_session(session_id)
- richer streaming events (delta pieces rather than the full buffer), change stream_consumer to receive incremental piece instead of buffer.
"""

from __future__ import annotations

import asyncio
import queue
import time
from typing import Any, Callable, Coroutine, Dict, Optional

# Project-specific utilities (same as original chat.py)
from gui.chat.handlers import (
    normalize_user_message_for_workflow,
    run_create_filename_workflow,
)
from gui.chat.session import (
    _Session,
    _sessions,
    _sessions_lock,
    append_chat_message_delta,
    build_chat_payload,
    create_session,
    from_snapshot,
    message_for_persist,
    reset_session,
    slugify_filename,
    suggest_initial_chat_path,
    to_snapshot,
    unique_path,
    write_chat_payload,
)
from gui.chat.ui.message_renderer import streaming_agent_opened_code_fence
from gui.chat.utils import _new_id, _now_ts
from gui.chat.utils.workflow_run_utils import _workflow_debug_log
from gui.components.settings import (
    get_auto_delegate_workflow_path,
    get_auto_delegation_is_allowed,
    get_chat_history_dir,
    get_chat_stream_ui_interval_ms,
    get_coding_is_allowed,
    get_contribution_is_allowed,
    get_llm_provider,
    get_llm_provider_config,
    get_mydata_dir,
    get_rag_embedding_model,
    get_rag_index_dir,
    get_training_config_path,
)
from runtime.run import run_workflow
from runtime.stream_ui_signals import CHAMELEON_STREAM_PREFIX, INLINE_STATUS_PREFIX
from units.pipelines.agent_orchestrator import orchestration_workflow_path

# Global session registry
# _sessions: Dict[str, _Session] = {}
# _sessions_lock = threading.Lock()

# Chat history dir + ui interval
_chat_history_dir = get_chat_history_dir()
_chat_history_dir.mkdir(parents=True, exist_ok=True)
_stream_ui_min_interval_s = max(0.016, float(get_chat_stream_ui_interval_ms()) / 1000.0)


def stop_run(session_id: str) -> None:
    """Signal stopping the currently active run by advancing the run token."""
    with _sessions_lock:
        s = _sessions.get(session_id)
        if s is None:
            return
        with s.run_lock:
            s.run_token += 1


def _append_message_to_session(
    s: _Session, role: str, content: str, meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    msg = {"id": _new_id(), "ts": _now_ts(), "role": role, "content": content}
    if meta:
        msg.update(meta)
    s.history.append(msg)
    # ensure path
    if s.chat_path is None:
        s.chat_path = suggest_initial_chat_path(_chat_history_dir)
    if s.chat_path is not None:
        try:
            append_chat_message_delta(s.chat_path, message_for_persist(msg))
        except Exception:
            pass
    return msg


def _schedule_name_from_first_message_async(s: _Session, first_message: str) -> None:
    if s.chat_path is None:
        return

    async def _run() -> None:
        base = ""
        try:
            provider = get_llm_provider(agent="default")
            cfg = get_llm_provider_config(agent="default") or {}
            resp = await asyncio.to_thread(
                run_create_filename_workflow, first_message, provider, cfg, 60.0
            )
            base = slugify_filename(resp) if resp else slugify_filename(first_message)
        except Exception:
            base = slugify_filename(first_message)
        try:
            old = s.chat_path
            if old is None:
                return
            new_path = unique_path(_chat_history_dir, base)
            if new_path != old:
                old.rename(new_path)
                s.chat_path = new_path
                # write full payload
                payload = build_chat_payload(
                    schema_version=3,
                    session_id=s.session_id,
                    created_at=s.created_at,
                    agent_selected="",
                    session_language=s.session_language,
                    chat_history_dir=_chat_history_dir,
                    messages=s.history,
                    get_llm_provider=lambda a: get_llm_provider(agent=a),
                    get_llm_provider_config=lambda a: (
                        get_llm_provider_config(agent=a) or {}
                    ),
                )
                write_chat_payload(new_path, payload)
        except Exception:
            pass

    asyncio.create_task(_run())


async def _run_workflow_with_streaming_for_session(
    s: _Session,
    run_fn: Callable[..., Any],
    workflow_path: str,
    *,
    run_token: Optional[int] = None,
    initial_inputs: Optional[Dict[str, Any]] = None,
    unit_param_overrides: Optional[Dict[str, Any]] = None,
    format: str = "dict",
    stream_consumer: Optional[Callable[[str, str], Coroutine[Any, Any, None]]] = None,
) -> Any:
    """Run workflow in thread and stream pieces to stream_consumer(session_id, piece)."""
    q: queue.Queue[Optional[str]] = queue.Queue()

    def stream_cb(p: Optional[str]) -> None:
        q.put(p)

    def run_in_thread():
        try:
            result = run_fn(
                workflow_path,
                initial_inputs=initial_inputs,
                unit_param_overrides=unit_param_overrides,
                format=format,
                stream_callback=stream_cb,
            )
        except Exception:
            s.applied_flag = False
            q.put(None)
            return None
        else:
            s.thread_result = result
            s.applied_flag = bool(getattr(result, "applied", True))
            q.put(None)
            return result

    async def consumer():
        last_paint = 0.0

        async def flush(force: bool = False):
            nonlocal last_paint
            if run_token is not None:
                with s.run_lock:
                    if run_token != s.run_token:
                        return
            now = time.perf_counter()
            if (not force) and (now - last_paint < _stream_ui_min_interval_s):
                return
            txt = s.stream_buffer
            if not s.stream_rich and streaming_agent_opened_code_fence(txt):
                s.stream_rich = True
            if stream_consumer:
                try:
                    await stream_consumer(s.session_id, txt)
                except Exception:
                    pass
            last_paint = now

        loop = asyncio.get_event_loop()
        while True:
            piece = await loop.run_in_executor(None, q.get)
            if piece is None:
                await flush(force=True)
                break
            with s.run_lock:
                if run_token is not None and run_token != s.run_token:
                    continue
            if piece.startswith(INLINE_STATUS_PREFIX):
                if stream_consumer:
                    try:
                        await stream_consumer(s.session_id, piece)
                    except Exception:
                        pass
                continue
            if piece.startswith(CHAMELEON_STREAM_PREFIX):
                continue
            s.stream_buffer += piece
            await flush(force=False)

    consumer_task = asyncio.create_task(consumer())
    thread_task = asyncio.to_thread(run_in_thread)
    await asyncio.gather(consumer_task, thread_task)
    return s.thread_result


async def handle_turn(
    session_id: Optional[str],
    user_message: str,
    messenger: str,
    *,
    graph_dict: Optional[Dict[str, Any]] = None,
    role_id: Optional[str] = None,
    stream_callback: Optional[Callable[[str, str], Coroutine[Any, Any, None]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Handle a user turn for the given session_id (creates session if needed).
    stream_callback: async fn(session_id, chunk_or_status)
    Returns orchestrator outputs dict or None on error.
    """
    sid = create_session(session_id)
    with _sessions_lock:
        s = _sessions[sid]

    message_for_workflow = normalize_user_message_for_workflow(user_message)
    turn_id = _new_id()
    _append_message_to_session(
        s, "user", user_message, meta={"turn_id": turn_id, "messenger": messenger}
    )

    if not s.has_sent_any:
        s.has_sent_any = True
        _schedule_name = _schedule_name_from_first_message_async
        _schedule_name(s, user_message)

    # default agent string when role_id is None
    agent = role_id or "default"

    # build context
    context = {
        "user_message": message_for_workflow,
        "messenger": messenger,
        "role_id": role_id,
        "history": list(s.history),
        "session_language": s.session_language,
        "last_apply_result": s.last_apply_result,
        "graph": graph_dict,
        "recent_changes": None,
        "use_current_graph": False,
        "provider": get_llm_provider(agent=agent),
        "cfg": get_llm_provider_config(agent=agent) or {},
        "rag_index_dir": str(get_rag_index_dir()),
        "rag_embedding_model": get_rag_embedding_model(),
        "mydata_dir": str(get_mydata_dir()),
        "coding_is_allowed": get_coding_is_allowed(),
        "contribution_is_allowed": get_contribution_is_allowed(),
        "training_config_path": get_training_config_path(),
        "auto_delegation_is_allowed": get_auto_delegation_is_allowed(),
        "auto_delegate_workflow_path": str(get_auto_delegate_workflow_path()),
    }

    # begin run
    with s.run_lock:
        s.run_token += 1
        run_token = s.run_token
        s.stream_buffer = ""
        s.stream_rich = False
        s.thread_result = None
        s.applied_flag = True

    try:
        result = await _run_workflow_with_streaming_for_session(
            s,
            run_workflow,
            str(orchestration_workflow_path()),
            run_token=run_token,
            initial_inputs={"inject_context": {"data": context}},
            unit_param_overrides=None,
            format="dict",
            stream_consumer=stream_callback,
        )
    except Exception:
        return None

    # ensure this run is still current
    with s.run_lock:
        if run_token != s.run_token:
            return None

    outputs = (result or {}).get("orchestrator") or {}
    # role output — store if present
    role_out = outputs.get("role")
    if isinstance(role_out, dict) and role_out.get("role_id"):
        # store if you want: s.some_role = role_out["role_id"]
        pass

    # error handling
    error_out = outputs.get("error")
    if isinstance(error_out, dict) and error_out.get("error"):
        _append_message_to_session(
            s,
            "agent",
            str(error_out["error"]),
            meta={
                "turn_id": turn_id,
                "agent": role_id,
                "source": "error",
                "error_type": "orchestrator_error",
            },
        )
        return outputs

    # final message handling
    msg_out = outputs.get("message")
    if isinstance(msg_out, dict) and msg_out.get("type") == "final":
        raw_msg = msg_out.get("message")
        msg = raw_msg if isinstance(raw_msg, dict) else {}
        new_lang = msg.get("session_language")
        if isinstance(new_lang, str):
            s.session_language = new_lang
            _workflow_debug_log(f"session_language updated → {new_lang!r}")
        s.last_apply_result = msg.get("last_apply_result")
        content = msg.get("content") or ""
        meta = {
            k: v for k, v in msg.items() if k not in ("content", "role", "id", "ts")
        }
        meta["turn_id"] = turn_id
        _append_message_to_session(s, "agent", content, meta=meta)

    return outputs
