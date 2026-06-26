"""
turn_driver (multi-session, thread-safe) is the main API entry point for messengers to connect,
which is a self-contained module that:

- Manages multiple sessions keyed by session_id (creates one if omitted).
- Runs workflows in threads and streams tokens to an async per-session callback.
- Maintains per-session history, last_apply_result, persistence, and filename suggestion.
- Exposes thread-safe APIs:
  - create_session(session_id: Optional[str]) -> str
  - get_session(session_id: str) -> Optional[_Session]
  - reset_session(session_id: str) -> None
  - stop_run(session_id: str) -> None
  - restore_session(session_id, *, path, payload) -> None
  - append_session_message(session_id, msg) -> None
  - persist_session(session_id, *, agent_selected) -> bool
  - handle_turn(session_id, user_message, messenger, *, graph_dict, role_id,
                recent_changes, pre_built_user_msg, on_rename,
                stream_callback) -> dict | None
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
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
    message_for_persist,
    slugify_filename,
    suggest_initial_chat_path,
    to_snapshot,
    unique_path,
    write_chat_payload,
)
from gui.chat.ui.message_renderer import streaming_agent_opened_code_fence
from gui.chat.utils import _new_id, _now_ts
from gui.chat.utils.workflow_run_utils import _workflow_debug_log
from gui.chat.zmq_jobs_client import publish_job_and_wait
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
from runtime.stream_ui_signals import CHAMELEON_STREAM_PREFIX, INLINE_STATUS_PREFIX
from runtime.zmq_messaging import ZmqTopics
from units.pipelines.agent_orchestrator import orchestration_workflow_path

logger = logging.getLogger(__name__)

# Chat history dir + ui interval
_chat_history_dir = get_chat_history_dir()
_chat_history_dir.mkdir(parents=True, exist_ok=True)
_stream_ui_min_interval_s = max(0.016, float(get_chat_stream_ui_interval_ms()) / 1000.0)

# the queue max size to handle requesets from messengers
STREAM_QUEUE_MAXSIZE = 128
ZMQ_JOB_PUB_ENDPOINT = "tcp://127.0.0.1:6664"
ZMQ_WORKFLOW_RESPONSE_ENDPOINT = "tcp://127.0.0.1:6674"
WORKFLOW_SERVER_AWAIT_TIMEOUT_S = 90


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


def _schedule_name_from_first_message_async(
    s: _Session,
    first_message: str,
    on_rename: Optional[Callable[[Path], None]] = None,
) -> None:
    """Schedule an async task to suggest and rename the chat file.

    on_rename is called (on the caller's event loop) after the file is successfully
    renamed, so the UI can update the title and recent-chats menu.
    """
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

                # build/write using a consistent serializable snapshot
                try:
                    snapshot = to_snapshot(s)
                    payload = build_chat_payload(
                        schema_version=3,
                        session_id=snapshot["session_id"],
                        created_at=snapshot["created_at"],
                        agent_selected="",
                        session_language=snapshot["session_language"],
                        chat_history_dir=_chat_history_dir,
                        messages=snapshot["history"],
                        get_llm_provider=lambda a: get_llm_provider(agent=a),
                        get_llm_provider_config=lambda a: (
                            get_llm_provider_config(agent=a) or {}
                        ),
                    )
                    write_chat_payload(new_path, payload)
                except Exception:
                    pass

                if on_rename is not None:
                    try:
                        on_rename(new_path)
                    except Exception:
                        pass
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
    loop = asyncio.get_running_loop()
    stream_q: asyncio.Queue[Optional[str]] = asyncio.Queue(STREAM_QUEUE_MAXSIZE)

    def stream_cb(p: Optional[str]) -> None:
        try:
            loop.call_soon_threadsafe(stream_q.put_nowait, p)
        except Exception:
            # queue full or loop closed; drop piece
            pass

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
            try:
                loop.call_soon_threadsafe(stream_q.put_nowait, None)
            except Exception:
                pass
            return None
        else:
            s.thread_result = result
            s.applied_flag = bool(getattr(result, "applied", True))
            try:
                loop.call_soon_threadsafe(stream_q.put_nowait, None)
            except Exception:
                pass
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
                    await asyncio.wait_for(
                        stream_consumer(s.session_id, txt), timeout=2.0
                    )
                except Exception:
                    pass
            last_paint = now

        while True:
            piece = await stream_q.get()
            if piece is None:
                await flush(force=True)
                break

            with s.run_lock:
                if run_token is not None and run_token != s.run_token:
                    continue

            if piece.startswith(INLINE_STATUS_PREFIX):
                if stream_consumer:
                    try:
                        await asyncio.wait_for(
                            stream_consumer(s.session_id, piece), timeout=2.0
                        )
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


# ---------------------------------------------------------------------------
# Session helpers (public API for chat.py)
# ---------------------------------------------------------------------------


def restore_session(session_id: str, *, path: Path, payload: Dict[str, Any]) -> None:
    """Restore a session from a loaded chat-file payload.

    Replaces history, session_language, created_at, last_apply_result, and
    chat_path in the existing session (identified by *session_id*). Any
    in-progress run is NOT cancelled — callers must ensure no run is active.
    """
    with _sessions_lock:
        s = _sessions.get(session_id)
    if s is None:
        return
    with s.run_lock:
        s.history.clear()
        for m in payload.get("messages") or []:
            if isinstance(m, dict):
                s.history.append(m)
        s.session_language = str(payload.get("session_language") or "")
        s.created_at = str(payload.get("created_at") or _now_ts())
        s.last_apply_result = payload.get("last_apply_result")
        s.chat_path = path
        s.has_sent_any = any(
            m.get("role") == "user" and (m.get("content") or "").strip()
            for m in s.history
            if isinstance(m, dict)
        )
        s.stream_buffer = ""
        s.stream_rich = False
        s.thread_result = None
        s.applied_flag = True


def append_session_message(session_id: str, msg: Dict[str, Any]) -> None:
    """Append a pre-built message dict to session history and the delta file.

    Use this for messages that bypass handle_turn (e.g. session-language
    command acknowledgements).
    """
    with _sessions_lock:
        s = _sessions.get(session_id)
    if s is None:
        return
    s.history.append(msg)
    if s.chat_path is None:
        s.chat_path = suggest_initial_chat_path(_chat_history_dir)
    if s.chat_path is not None:
        try:
            append_chat_message_delta(s.chat_path, message_for_persist(msg))
        except Exception:
            pass


def persist_session(session_id: str, *, agent_selected: Optional[str] = None) -> bool:
    """Write a full history snapshot for the session to disk. Returns True on success."""
    with _sessions_lock:
        s = _sessions.get(session_id)
    if s is None or s.chat_path is None:
        return False
    try:
        snapshot = to_snapshot(s)
        payload = build_chat_payload(
            schema_version=3,
            session_id=snapshot["session_id"],
            created_at=snapshot["created_at"],
            agent_selected=agent_selected or "",
            session_language=snapshot["session_language"],
            chat_history_dir=_chat_history_dir,
            messages=snapshot["history"],
            get_llm_provider=lambda a: get_llm_provider(agent=a),
            get_llm_provider_config=lambda a: get_llm_provider_config(agent=a) or {},
        )
        return write_chat_payload(s.chat_path, payload)
    except Exception:
        return False


async def handle_turn(
    session_id: Optional[str],
    user_message: str,
    messenger: str,
    *,
    graph_dict: Optional[Dict[str, Any]] = None,
    role_id: Optional[str] = None,
    recent_changes: Optional[str] = None,
    pre_built_user_msg: Optional[Dict[str, Any]] = None,
    on_rename: Optional[Callable[[Path], None]] = None,
    stream_callback: Optional[Callable[[str, str], Coroutine[Any, Any, None]]] = None,
) -> Optional[Dict[str, Any]]:
    import logging

    logger = logging.getLogger(__name__)

    sid = create_session(session_id)
    with _sessions_lock:
        s = _sessions[sid]

    run_token = None  # so we can log in finally if needed

    def _ensure_chat_path() -> None:
        if s.chat_path is None:
            s.chat_path = suggest_initial_chat_path(_chat_history_dir)

    def _append_agent_placeholder_if_needed(
        *,
        turn_id: str,
        assistant_message_id: str,
        agent_meta: Dict[str, Any],
    ) -> None:
        """
        Best-effort: append a placeholder so follow-up turns have something to render
        even if the final message is missed/arrives later.
        """
        try:
            if s.chat_path is not None:
                _append_message_to_session(
                    s, "agent", "", meta=agent_meta | {"id": assistant_message_id}
                )
                try:
                    append_chat_message_delta(
                        s.chat_path,
                        {
                            "role": "agent",
                            "id": assistant_message_id,
                            "content_delta": "",
                            "meta": agent_meta,
                        },
                    )
                except Exception:
                    pass
            else:
                _append_message_to_session(
                    s, "agent", "", meta=agent_meta | {"id": assistant_message_id}
                )
        except Exception:
            pass

    async def _best_effort_stream_update(
        *,
        assistant_message_id: str,
        turn_id: str,
        agent_meta: Dict[str, Any],
        content_so_far: str,
    ) -> None:
        """
        Best-effort: update the in-progress assistant message so streaming is visible
        and persisted enough for follow-up renders.
        """
        try:
            if s.chat_path is None:
                _ensure_chat_path()

            if s.chat_path is None:
                return

            try:
                append_chat_message_delta(
                    s.chat_path,
                    {
                        "role": "agent",
                        "id": assistant_message_id,
                        "content_delta": "",
                        "meta": agent_meta,
                    },
                )
            except Exception:
                pass

            if stream_callback is not None:
                await stream_callback(s.session_id, content_so_far)
        except Exception:
            pass

    def _extract_final_message_and_content(
        outputs: Dict[str, Any],
    ) -> tuple[Optional[Dict[str, Any]], str]:
        msg_out = outputs.get("message")

        # Case: the outputs itself is {"type":"final","message": {...}}
        if (
            isinstance(outputs, dict)
            and outputs.get("type") == "final"
            and isinstance(msg_out, dict)
        ):
            return msg_out, (msg_out.get("content") or "")

        return None, ""

    try:
        with s.run_lock:
            if s.busy:
                return None
            s.busy = True

        message_for_workflow = normalize_user_message_for_workflow(user_message)

        if pre_built_user_msg is not None:
            turn_id = str(pre_built_user_msg.get("turn_id") or _new_id())
            s.history.append(pre_built_user_msg)
            if s.chat_path is None:
                s.chat_path = suggest_initial_chat_path(_chat_history_dir)
            if s.chat_path is not None:
                try:
                    append_chat_message_delta(
                        s.chat_path, message_for_persist(pre_built_user_msg)
                    )
                except Exception:
                    pass
        else:
            turn_id = _new_id()
            _append_message_to_session(
                s,
                "user",
                user_message,
                meta={"turn_id": turn_id, "messenger": messenger},
            )

        if not s.has_sent_any:
            s.has_sent_any = True
            _schedule_name_from_first_message_async(
                s, user_message, on_rename=on_rename
            )

        agent = role_id or "default"

        context = {
            "user_message": message_for_workflow,
            "messenger": messenger,
            "role_id": role_id,
            "history": list(s.history),
            "session_language": s.session_language,
            "last_apply_result": s.last_apply_result,
            "graph": graph_dict,
            "recent_changes": recent_changes,
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

        assistant_message_id = _new_id()
        assistant_meta_base = {
            "turn_id": turn_id,
            "agent": role_id,
            "source": "stream",
        }
        first_token_persisted = False
        content_accum = ""

        with s.run_lock:
            s.run_token += 1
            run_token = s.run_token
            s.stream_buffer = ""
            s.stream_rich = False
            s.thread_result = None
            s.applied_flag = True

        run_id = f"{s.session_id}:{run_token}"
        wf_path = str(orchestration_workflow_path())
        topics = ZmqTopics()

        logger.info(
            "handle_turn: start session_id=%r run_id=%r messenger=%r role_id=%r job_pub_endpoint=%r topics.job=%r response_endpoint=%r wf_path=%r",
            s.session_id,
            run_id,
            messenger,
            role_id,
            ZMQ_JOB_PUB_ENDPOINT,
            topics.job,
            ZMQ_WORKFLOW_RESPONSE_ENDPOINT,
            wf_path,
        )

        def _is_stale() -> bool:
            with s.run_lock:
                return f"{s.session_id}:{s.run_token}" != run_id

        async def _token_cb(_cb_session_id: str, token_piece: str) -> None:
            nonlocal first_token_persisted, content_accum

            if _is_stale():
                logger.info(
                    "token_cb: STALE session_id=%r run_id=%r run_token_now=%r token_prefix=%r",
                    s.session_id,
                    run_id,
                    s.run_token,
                    token_piece[:40],
                )
                return

            try:
                if token_piece.startswith(INLINE_STATUS_PREFIX):
                    if stream_callback is not None:
                        await stream_callback(s.session_id, token_piece)
                    return

                if token_piece.startswith(CHAMELEON_STREAM_PREFIX):
                    return

                with s.run_lock:
                    s.stream_buffer += token_piece
                    content_accum += token_piece

                if not first_token_persisted:
                    first_token_persisted = True

                    with s.run_lock:
                        _ensure_chat_path()

                    _append_agent_placeholder_if_needed(
                        turn_id=turn_id,
                        assistant_message_id=assistant_message_id,
                        agent_meta=assistant_meta_base
                        | {"id": assistant_message_id, "source": "stream_start"},
                    )

                await _best_effort_stream_update(
                    assistant_message_id=assistant_message_id,
                    turn_id=turn_id,
                    agent_meta=assistant_meta_base | {"id": assistant_message_id},
                    content_so_far=s.stream_buffer,
                )

            except Exception:
                pass

        try:
            result = await asyncio.wait_for(
                publish_job_and_wait(
                    job_pub_endpoint=ZMQ_JOB_PUB_ENDPOINT,
                    job_topic=topics.job,
                    response_endpoint=ZMQ_WORKFLOW_RESPONSE_ENDPOINT,
                    run_id=run_id,
                    workflow_path=wf_path,
                    initial_inputs={"inject_context": {"data": context}},
                    unit_param_overrides=None,
                    format="dict",
                    execution_timeout_s=None,
                    token_callback=_token_cb,
                    session_id=s.session_id,
                    is_stale=_is_stale,
                    topics=topics,
                ),
                timeout=WORKFLOW_SERVER_AWAIT_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.error(
                "handle_turn: workflow response timeout session_id=%r run_id=%r",
                s.session_id,
                run_id,
            )
            _append_message_to_session(
                s,
                "agent",
                "Timed out waiting for workflow response. Please retry.",
                meta={"turn_id": turn_id, "agent": role_id, "source": "timeout"},
            )
            return {
                "orchestrator": {
                    "error": {"error": "timeout_waiting_for_workflow_response"}
                }
            }
        except Exception:
            logger.exception("handle_turn: publish_job_and_wait failed")
            return None

        with s.run_lock:
            logger.info(
                "handle_turn: returned session_id=%r run_id=%r run_token_now=%r",
                s.session_id,
                run_id,
                s.run_token,
            )
            is_stale_now = f"{s.session_id}:{s.run_token}" != run_id

        outputs = (result or {}).get("orchestrator") or {}
        logger.info(
            "handle_turn: outputs session_id=%r run_id=%r outputs_keys=%r outputs=%r",
            s.session_id,
            run_id,
            list(outputs.keys()),
            outputs,
        )

        if is_stale_now:
            return outputs

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
            logger.error(
                "handle_turn: orchestrator error session_id=%r run_id=%r err=%r",
                s.session_id,
                run_id,
                error_out.get("error"),
            )
            return outputs

        # --- FIX: correctly wire message/token payload after ZMQ result ---
        raw_msg, content_from_msg = _extract_final_message_and_content(outputs)

        if raw_msg is not None:
            new_lang = raw_msg.get("session_language")
            if isinstance(new_lang, str):
                s.session_language = new_lang
                _workflow_debug_log(f"session_language updated → {new_lang!r}")
            s.last_apply_result = raw_msg.get("last_apply_result")

            content = raw_msg.get("content") or content_from_msg or ""
            meta = {
                k: v
                for k, v in raw_msg.items()
                if k not in ("content", "role", "id", "ts")
            }
            meta["turn_id"] = turn_id
            meta["agent"] = role_id

            _append_message_to_session(
                s,
                "agent",
                content,
                meta=meta | {"id": assistant_message_id, "source": "final"},
            )

            logger.info(
                "handle_turn: final message stored session_id=%r run_id=%r content_len=%d",
                s.session_id,
                run_id,
                len(content),
            )
            return outputs

        # If unit only returned token/full text under outputs["token"]
        token_out = outputs.get("token")
        if isinstance(token_out, dict):
            full_text = token_out.get("token") or ""
            if full_text:
                _append_message_to_session(
                    s,
                    "agent",
                    full_text,
                    meta={"turn_id": turn_id, "agent": role_id, "source": "token_full"},
                )
                return outputs

        # Fall back: no parsable final message payload
        final_msg = outputs.get("message")
        final_content = (
            final_msg if isinstance(final_msg, str) else "No final message returned."
        )

        _append_message_to_session(
            s,
            "agent",
            final_content,
            meta={"turn_id": turn_id, "agent": role_id, "source": "no_final"},
        )
        return outputs

    finally:
        with s.run_lock:
            s.busy = False
