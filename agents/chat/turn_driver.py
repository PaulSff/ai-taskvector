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
from collections.abc import Awaitable, Callable, Coroutine
from pathlib import Path
from typing import cast

# Project-specific utilities (same as original chat.py)
from agents.chat.handlers import (
    normalize_user_message_for_workflow,
    run_create_filename_workflow,
)
from agents.chat.session import (
    _Session,
    _sessions,
    _sessions_lock,
    append_chat_message_delta,
    build_chat_payload,
    create_session,
    get_typed,
    message_for_persist,
    slugify_filename,
    suggest_initial_chat_path,
    to_snapshot,
    unique_path,
    write_chat_payload,
)
from agents.chat.utils.workflow_run_utils import (
    _workflow_debug_log,  # pyright: ignore[reportPrivateUsage]
)
from agents.chat.zmq_jobs_client import publish_job_and_wait
from agents.follow_ups import USER_MESSAGE_PLANNING_PREFIX
from gui.components.settings import (
    get_agentic_loop_execution_timeout_s,
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
from gui.utils import _new_id, _now_ts
from runtime.stream_ui_signals import CHAMELEON_STREAM_PREFIX, INLINE_STATUS_PREFIX
from services.zmq.zmq_messaging import ZmqTopics
from units.pipelines.agent_orchestrator import orchestration_workflow_path

logger = logging.getLogger(__name__)

# Timeout (from settings) to wait for the final message to return from the orchestration pipeline
ORCHESTRATION_PIPELINE_EXECUTION_TIMEOUT_S = get_agentic_loop_execution_timeout_s()

# Chat history dir + ui interval
_chat_history_dir = get_chat_history_dir()
_chat_history_dir.mkdir(parents=True, exist_ok=True)
_stream_ui_min_interval_s = max(0.016, float(get_chat_stream_ui_interval_ms()) / 1000.0)

def _append_message_to_session(
    s: _Session, role: str, content: str, meta: dict[str, object] | None = None
) -> dict[str, object]:
    msg: dict[str, object] = {
        "id": _new_id(),
        "ts": _now_ts(),
        "role": role,
        "content": content,
    }
    if meta:
        msg.update(meta)
    s.history.append(msg)
    # ensure path
    if s.chat_path is None:
        s.chat_path = suggest_initial_chat_path(_chat_history_dir)

    try:
        _ = append_chat_message_delta(s.chat_path, message_for_persist(msg))
    except (OSError, TypeError, ValueError):
        pass
    return msg



# Assuming these are imported from your project
# from gui.utils import slugify_filename, unique_path, to_snapshot, build_chat_payload, write_chat_payload
# from gui.llm import get_llm_provider, get_llm_provider_config, run_create_filename_workflow
# from gui.config import _chat_history_dir

def _schedule_name_from_first_message_async(
    s: _Session,
    first_message: str,
    on_rename: Callable[[Path], None] | None = None,
) -> None:
    """Schedule an async task to suggest and rename the chat file."""
    if s.chat_path is None:
        return

    async def _run() -> None:
        base = ""
        try:
            provider = get_llm_provider(agent="default")
            cfg = cast(dict[str, object], get_llm_provider_config(agent="default") or {})
            resp = await asyncio.to_thread(
                run_create_filename_workflow, first_message, provider, cfg, 60.0
            )
            base = slugify_filename(resp) if resp else slugify_filename(first_message)

        except (ImportError, AttributeError, TypeError, ValueError, TimeoutError):
            base = slugify_filename(first_message)

        try:
            old = s.chat_path
            if old is None:
                return

            # Now 'base' is actually populated from the LLM or the first message
            new_path = unique_path(_chat_history_dir, base)

            old_path = Path(old)
            new_path = Path(new_path)

            if new_path != old_path:
                if not old_path.exists():
                    logger.warning("Chat history file missing; cannot rename: %s", old_path)
                    s.chat_path = new_path
                else:
                    s.chat_path = old_path.rename(new_path)

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
                        # FIX 3: Cast inside the lambda to avoid "Unknown" error
                        get_llm_provider_config=lambda a: cast(
                            dict[str, object], get_llm_provider_config(agent=a) or {}
                        ),
                    )
                    _ = write_chat_payload(new_path, payload)
                except (ImportError, AttributeError, TypeError, ValueError, TimeoutError):
                    pass

                if on_rename is not None:
                    try:
                        on_rename(new_path)
                    except (ImportError, AttributeError, TypeError, ValueError, TimeoutError):
                        pass

        except (ImportError, AttributeError, TypeError, ValueError, TimeoutError):
            pass

    # Note: In production, we should store a reference to this task to prevent
    # it from being garbage collected mid-execution.
    _ = asyncio.create_task(_run())


# ---------------------------------------------------------------------------
# Session helpers (public API for chat.py)
# ---------------------------------------------------------------------------

def restore_session(session_id: str, *, path: Path, payload: dict[str, object]) -> None:
    """Restore a session from a loaded chat-file payload."""
    with _sessions_lock:
        s = _sessions.get(session_id)

    if s is None:
        return

    with s.run_lock:
        # 1. Fix: Narrow payload.get("messages") to list[object]
        s.history.clear()
        raw_msgs = payload.get("messages")
        if isinstance(raw_msgs, list):
            # Cast to list[object] so we can iterate without "Unknown" errors
            for m in cast(list[object], raw_msgs):
                if isinstance(m, dict):
                    # Cast to dict[str, object] before appending to s.history
                    s.history.append(cast(dict[str, object], m))

        #  Use get_typed helper
        s.session_language = get_typed(payload, "session_language", s.session_language, str)
        s.created_at = get_typed(payload, "created_at", s.created_at, str)

        # 3. Handle the complex dict result
        last_res = payload.get("last_apply_result")
        if isinstance(last_res, dict):
            s.last_apply_result = cast(dict[str, object], last_res)
        else:
            s.last_apply_result = None

        s.chat_path = path

        # 4. Explicit loop for has_sent_any to avoid "Unknown" generator errors
        sent_any = False
        for m in s.history:
            role = m.get("role")
            content = m.get("content")

            if isinstance(role, str) and role == "user" and isinstance(content, str) and content.strip():
                sent_any = True
                break

        s.has_sent_any = sent_any

        s.stream_buffer = ""
        s.stream_rich = False
        s.thread_result = None
        s.applied_flag = True


def append_session_message(session_id: str, msg: dict[str, object]) -> None:
    """Append a pre-built message dict to session history and the delta file.

    Use this for messages that bypass handle_turn (e.g. session-language
    command acknowledgements).
    """
    with _sessions_lock:
        s = _sessions.get(session_id)

    if s is None:
        return

    # msg is dict[str, object], which matches s.history's type
    s.history.append(msg)

    if s.chat_path is None:
        s.chat_path = suggest_initial_chat_path(_chat_history_dir)

    try:
        # Assign to '_' because the function returns a bool that isn't used
        _ = append_chat_message_delta(s.chat_path, message_for_persist(msg))
    except OSError as e:
        # e.g., file/path issues
        logger.warning("Failed to append chat delta: %s", e)




def persist_session(session_id: str, *, agent_selected: str | None = None) -> bool:
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
            get_llm_provider_config=lambda a: cast(
                dict[str, object], get_llm_provider_config(agent=a) or {}
            ),
        )

        return write_chat_payload(s.chat_path, payload)

    except KeyError as e:
        # snapshot missing required fields
        logger.warning("Snapshot missing key: %s", e)
        return False

    except (OSError) as e:
        # filesystem / IO problems writing payload
        logger.warning("Failed to write chat payload: %s", e)
        return False

    except ValueError as e:
        # build_chat_payload validation failures
        logger.warning("Invalid chat payload: %s", e)
        return False


async def handle_turn(
    session_id: str | None,
    user_message: str,
    messenger: str,
    *,
    planning_mode: bool = False,
    graph_dict: dict[str, object] | None = None,
    role_id: str | None = None,
    recent_changes: str | None = None,
    pre_built_user_msg: dict[str, object] | None = None,
    on_rename: Callable[[Path], None] | None = None,
    stream_callback: Callable[[str, str], Coroutine[object, object, None]] | None = None,
    on_apply: Callable[[dict[str, object]], Coroutine[object, object, None]] | None = None,
    on_turn_status: Callable[[dict[str, object]], Coroutine[object, object, None]] | None = None,
) -> dict[str, object] | None:
    import logging

    logger = logging.getLogger(__name__)

    sid = create_session(session_id)
    with _sessions_lock:
        s = _sessions[sid]
    s.messenger = messenger

    run_token = None  # so we can log in finally if needed
    turn_id: str | None = None

    def _ensure_chat_path() -> None:
        if s.chat_path is None:
            s.chat_path = suggest_initial_chat_path(_chat_history_dir)

    def _append_agent_placeholder_if_needed(
        *,
        turn_id: str,
        assistant_message_id: str,
        agent_meta: dict[str, object],
    ) -> None:
        """
        Best-effort: append a placeholder so follow-up turns have something to render
        even if the final message is missed/arrives later.
        """
        try:
            if s.chat_path is not None:
                _ = _append_message_to_session(
                    s, "agent", "", meta=agent_meta | {"id": assistant_message_id}
                )

                try:
                    _ = append_chat_message_delta(
                        s.chat_path,
                        {
                            "role": "agent",
                            "id": assistant_message_id,
                            "content_delta": "",
                            "meta": agent_meta,
                        },
                    )
                except Exception:
                    logger.exception(
                        "Failed to append chat message delta (chat_path set). assistant_message_id=%s meta=%r",
                        assistant_message_id, agent_meta
                    )
                    # optionally: raise
                    # raise
            else:
                _ = _append_message_to_session(
                    s, "agent", "", meta=agent_meta | {"id": assistant_message_id}
                )

        except Exception:
            logger.exception(
                "Failed to append agent message to session. assistant_message_id=%s meta=%r chat_path=%r",
                assistant_message_id, agent_meta, getattr(s, "chat_path", None)
            )

    async def _best_effort_stream_update(
        *,
        assistant_message_id: str,
        turn_id: str,
        agent_meta: dict[str, object],
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
                _ = append_chat_message_delta(
                    s.chat_path,
                    {
                        "role": "agent",
                        "id": assistant_message_id,
                        "content_delta": "",
                        "meta": agent_meta,
                    },
                )
            except Exception:
                logger.exception(
                    "append_chat_message_delta failed. chat_path=%r assistant_message_id=%r agent_meta=%r",
                    s.chat_path, assistant_message_id, agent_meta
                )

            if stream_callback is not None:
                await stream_callback(s.session_id, content_so_far)

        except Exception:
            logger.exception(
                "Agent streaming block failed. session_id=%r chat_path=%r assistant_message_id=%r",
                getattr(s, "session_id", None), getattr(s, "chat_path", None), assistant_message_id
            )

    def _extract_in_progress_from_batch_payload(
        payload: dict[str, object],
    ) -> tuple[dict[str, object] | None, str]:
        """
        payload is what publish_job_and_wait receives on topics.update_batch.
        Expected structure (from BatchUpdatePublisher.publish_progress):
          {
            "message": {
              "type": "in_progress",
              "message": { ... inner ... }
            },
            "run_id": ...
          }
        Returns (inner_message_obj, content_string).
        """
        msg_wrap = payload.get("message")
        if not isinstance(msg_wrap, dict):
            return None, ""

        # FIX: Cast wrapper to remove "Unknown" status
        msg_wrap_typed = cast(dict[str, object], msg_wrap)

        # .get("type") returns 'object | None' instead of 'Unknown'
        # We check if it's a string and equals "in_progress"
        msg_type = msg_wrap_typed.get("type")
        if not (isinstance(msg_type, str) and msg_type == "in_progress"):
            return None, ""

        # Handle the inner message
        inner = msg_wrap_typed.get("message")
        if not isinstance(inner, dict):
            return None, ""

        # Cast inner message to remove "Unknown" status
        inner_typed = cast(dict[str, object], inner)

        # 3. Extract content safely
        raw_content = inner_typed.get("content")
        content_str = raw_content if isinstance(raw_content, str) else ""
        # inner_typed is dict[str, object], content_str is str
        return inner_typed, content_str

    def _extract_final_message_and_content(
        outputs: dict[str, object],
    ) -> tuple[dict[str, object] | None, str]:

        def _maybe_final_from_msg_wrap(
            msg_wrap: object,
        ) -> tuple[dict[str, object] | None, str]:
            # Handles: {"type":"final", "message": {...}}
            if not isinstance(msg_wrap, dict):
                return None, ""

            msg_wrap_typed = cast(dict[str, object], msg_wrap)

            # Narrow msg_type to str before comparing
            msg_type = msg_wrap_typed.get("type")
            is_final = isinstance(msg_type, str) and msg_type == "final"

            if is_final:
                # Case A: Nested message structure
                inner = msg_wrap_typed.get("message")
                if isinstance(inner, dict):
                    inner_typed = cast(dict[str, object], inner)

                    # Narrow content to str
                    raw_content = inner_typed.get("content")
                    content_str = raw_content if isinstance(raw_content, str) else ""

                    return inner_typed, content_str

                # Case B: Flattened message structure
                if any(k in msg_wrap_typed for k in ("content", "role", "id")):
                    raw_content = msg_wrap_typed.get("content")
                    content_str = raw_content if isinstance(raw_content, str) else ""

                    return msg_wrap_typed, content_str

            return None, ""

        # Most common: {"type":"final","message":{...}}
        msg, content = _maybe_final_from_msg_wrap(outputs)
        if msg is not None:
            return msg, content

        # nesting: outputs["orchestrator"]["message"] -> {type, message}
        orch = outputs.get("orchestrator")
        if isinstance(orch, dict):
            # Cast orch to dict[str, object] so orch_msg is not 'Unknown'
            orch_typed = cast(dict[str, object], orch)
            orch_msg = orch_typed.get("message")

            # Now orch_msg is 'object | None', which _maybe_final_from_msg_wrap accepts
            msg, content = _maybe_final_from_msg_wrap(orch_msg)
            if msg is not None:
                return msg, content

            # Sometimes: outputs["orchestrator"]["message"]["message"] directly
            if isinstance(orch_msg, dict):
                orch_msg_typed = cast(dict[str, object], orch_msg)
                inner = orch_msg_typed.get("message")

                if isinstance(inner, dict):
                    inner_typed = cast(dict[str, object], inner)
                    if any(k in inner_typed for k in ("content", "role", "id")):
                        # Narrow content to str
                        raw_content = inner_typed.get("content")
                        content_str = raw_content if isinstance(raw_content, str) else ""
                        return inner_typed, content_str

        # 2. Handle direct message dicts
        raw_m = outputs.get("message")
        if isinstance(raw_m, dict):
            m_typed = cast(dict[str, object], raw_m)
            if any(k in m_typed for k in ("content", "role", "id")):
                # Narrow content to str
                raw_content = m_typed.get("content")
                content_str = raw_content if isinstance(raw_content, str) else ""
                return m_typed, content_str

        return None, ""

    last_graph_sig: str | None = None

    async def _maybe_apply_graph(inner_msg: dict[str, object]) -> None:
        """Apply graph updates to canvas via on_apply or the global graph bridge."""
        apply_cb = on_apply
        if apply_cb is None:
            from agents.chat.graph_bridge import apply_graph_from_turn

            async def _bridge_apply(msg: dict[str, object]) -> None:
               _ = await apply_graph_from_turn(msg)

            apply_cb = _bridge_apply
        await _apply_mid_run_if_present(inner_msg, apply_cb=apply_cb)

    async def _apply_mid_run_if_present(
        inner_msg: dict[str, object],
        *,
        apply_cb: Callable[[dict[str, object]], Awaitable[None]],
    ) -> None:
        """
        Best-effort graph/state apply during in-progress.
        Also optionally notifies UI via on_apply when a graph is present.
        """
        apply_val = inner_msg.get("apply")

        # We use cast(dict[str, object], ...) to tell the type checker that
        # the keys are strings, resolving the "list[Unknown]" warning.
        apply_keys = (
            list(cast(dict[str, object], apply_val).keys())
            if isinstance(apply_val, dict)
            else None
        )

        logger.info(
            "handle_turn: mid_run apply graph_present=%r apply_meta_keys=%r",
            bool(inner_msg.get("graph")),
            apply_keys,
        )


        try:
            nonlocal last_graph_sig

            # Use cast to define exactly what these objects are.
            # We use dict[str, object] and list[object] to avoid using 'Any'.
            graph = inner_msg.get("graph")
            apply_meta = cast(dict[str, object], inner_msg.get("apply") or {})
            parsed_edits = cast(list[object], inner_msg.get("parsed_edits") or [])
            last_apply_result = cast(dict[str, object], inner_msg.get("last_apply_result") or {})
            run_output = cast(dict[str, object], inner_msg.get("run_output") or {})

            # keep your existing "when to apply" condition, but only for session updates
            if (
                graph is None
                and not apply_meta
                and not parsed_edits
                and not run_output
                and not last_apply_result
            ):
                return

            new_lang = inner_msg.get("session_language")
            if isinstance(new_lang, str):
                s.session_language = new_lang
                s.last_apply_result = last_apply_result

            # UI update hook (only when graph exists) — emit repeatedly on graph changes
            if graph is not None:
                try:
                    sig = getattr(graph, "signature", None)
                    if sig is None:
                        sig = repr(graph)
                except (AttributeError, TypeError):
                    sig = repr(type(graph))

                if sig != last_graph_sig:
                    last_graph_sig = sig
                    await apply_cb(inner_msg)

        except Exception:
            logger.exception("Error while processing inner_msg; graph=%r", inner_msg.get("graph"))
            # optionally: raise

    try:
        with s.run_lock:
            if s.busy:
                return None
            s.busy = True

        message_for_workflow = normalize_user_message_for_workflow(user_message)
        # Prepend the Planning prfix to enable the Planner
        if planning_mode:
            message_for_workflow = f"{USER_MESSAGE_PLANNING_PREFIX}\n\n{message_for_workflow}"

        if pre_built_user_msg is not None:
            turn_id = str(pre_built_user_msg.get("turn_id") or _new_id())
            s.history.append(pre_built_user_msg)
            if s.chat_path is None:
                s.chat_path = suggest_initial_chat_path(_chat_history_dir)
                try:
                    _ = append_chat_message_delta(
                        s.chat_path, message_for_persist(pre_built_user_msg)
                    )
                except (OSError) as e:
                    # disk/path problems, transient FS issues
                    logger.warning("Failed to append chat message delta: %s", e)
                except (TypeError, ValueError) as e:
                    # bad message structure / serialization issues
                    logger.error("Failed to serialize message for persist: %s", e)
                    raise
        else:
            turn_id = _new_id()
            _ = _append_message_to_session(
                s,
                "user",
                user_message,
                meta={"turn_id": turn_id, "messenger": messenger},
            )
        # hook up the UI to provide the status
        if on_turn_status is not None:
            try:
                await on_turn_status(
                    {
                        "status": "running",
                        "messenger": messenger,
                        "turn_id": turn_id,
                        "session_id": s.session_id,
                    }
                )
            except (ConnectionError, TimeoutError) as e:
                logger.warning("on_turn_status failed (transient): %s", e)
            except (OSError) as e:
                logger.warning("on_turn_status failed (I/O): %s", e)


        if not s.has_sent_any:
            s.has_sent_any = True
            _schedule_name_from_first_message_async(
                s, user_message, on_rename=on_rename
            )

        agent = role_id or "default"

        context: dict[str, object] = {
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
            "handle_turn: start session_id=%r run_id=%r messenger=%r role_id=%r topics.job=%r wf_path=%r",
            s.session_id,
            run_id,
            messenger,
            role_id,
            topics.job,
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
                    # Unify behavior with the first turn: treat it as content to stream.
                    # Best-effort: strip the prefix if it’s part of the wire format.
                    token_piece = token_piece[len(CHAMELEON_STREAM_PREFIX) :]
                    if not token_piece:
                        return

                with s.run_lock:
                    s.stream_buffer += token_piece
                    content_accum += token_piece

                if not first_token_persisted:
                    first_token_persisted = True
                    # hook up UI
                    if on_turn_status is not None:
                        try:
                            await on_turn_status(
                                {
                                    "status": "working",
                                    "messenger": messenger,
                                    "turn_id": turn_id,
                                    "session_id": s.session_id,
                                }
                            )
                        except (ConnectionError, TimeoutError, OSError) as e:
                            logger.warning("on_turn_status(status=working) failed: %s", e)

                    with s.run_lock:
                        _ensure_chat_path()

                    _append_agent_placeholder_if_needed(
                        turn_id=turn_id,
                        assistant_message_id=assistant_message_id,
                        agent_meta=cast(
                            dict[str, object],
                            assistant_meta_base | {"id": assistant_message_id, "source": "stream_start"}
                        ),
                    )

                await _best_effort_stream_update(
                    assistant_message_id=assistant_message_id,
                    turn_id=turn_id,
                    agent_meta=cast(
                        dict[str, object],
                        assistant_meta_base | {"id": assistant_message_id}
                    ),
                    content_so_far=s.stream_buffer,
                )

            except (ConnectionError, TimeoutError, OSError):
                logger.exception(
                    "Stream update failed (turn_id=%r, assistant_message_id=%r)",
                    turn_id,
                    assistant_message_id,
                )

        async def _in_progress_batch_cb(payload: dict[str, object]) -> None:
            if _is_stale():
                return
            try:
                inner_msg, content = _extract_in_progress_from_batch_payload(payload)
                logger.info(
                    "handle_turn: in_progress_batch run_id=%r inner_keys=%r graph_present=%r content_len=%d",
                    payload.get("run_id"),
                    list(inner_msg.keys()) if isinstance(inner_msg, dict) else None,
                    bool(inner_msg.get("graph")) if isinstance(inner_msg, dict) else False,
                    len(content or ""),
                )
                if inner_msg is None:
                    return

                inner_id = inner_msg.get("id") or assistant_message_id

                new_lang = inner_msg.get("session_language")
                if isinstance(new_lang, str):
                    s.session_language = new_lang

                last_apply_result = inner_msg.get("last_apply_result")
                if isinstance(last_apply_result, dict):
                    s.last_apply_result = last_apply_result

                _ = _append_message_to_session(
                    s,
                    "agent",
                    content,
                    meta={
                        "turn_id": inner_msg.get("turn_id") or turn_id,
                        "agent": role_id,
                        "source": inner_msg.get("source") or "in_progress",
                        "apply": inner_msg.get("apply") or {},
                        "id": inner_id,
                    },
                )

                if on_turn_status is not None:
                    try:
                        await on_turn_status(
                            {
                                "status": "applying",
                                "messenger": messenger,
                                "turn_id": turn_id,
                                "session_id": s.session_id,
                            }
                        )
                    except (ConnectionError, TimeoutError, OSError):
                        logger.exception(
                            "on_turn_status(status=applying) failed (turn_id=%r, session_id=%r)",
                            turn_id,
                            s.session_id,
                        )

                await _maybe_apply_graph(inner_msg)

            except (ConnectionError, TimeoutError, OSError, ValueError, TypeError):
                logger.exception(
                    "in_progress_batch_cb failed (run_id=%r, turn_id=%r)",
                    payload.get("run_id"),
                    turn_id,
                )
                # best-effort: swallow known runtime issues
            except Exception:
                logger.exception("Unexpected error in in_progress_batch_cb (run_id=%r, turn_id=%r)", payload.get("run_id"), turn_id)
                raise


        try:
            result = await publish_job_and_wait(
                run_id=run_id,
                workflow_path=wf_path,
                initial_inputs={"inject_context": {"data": context}},
                unit_param_overrides=None,
                format="dict",
                execution_timeout_s=ORCHESTRATION_PIPELINE_EXECUTION_TIMEOUT_S,
                token_callback=_token_cb,
                session_id=s.session_id,
                is_stale=_is_stale,
                topics=topics,
                in_progress_callback=_in_progress_batch_cb,
            )

        except (TimeoutError):
            logger.error(
                "handle_turn: workflow response timeout session_id=%r run_id=%r",
                s.session_id,
                run_id,
            )
            _ = _append_message_to_session(
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

        outputs = cast(
            dict[str, object],
            (result or {}).get("orchestrator") or {}
        )

        logger.info(
            "handle_turn: outputs session_id=%r run_id=%r outputs_keys=%r",
            s.session_id,
            run_id,
            list(outputs.keys()),
        )

        if is_stale_now:
            return outputs

        error_out = outputs.get("error")

        if isinstance(error_out, dict):
            # 1. Cast to resolve 'Unknown' types immediately
            error_out = cast(dict[str, object], error_out)

            # 2. Extract the error message to a variable
            error_msg = error_out.get("error")

            if error_msg:
                _ = _append_message_to_session(
                    s,
                    "agent",
                    str(error_msg), # Now str() is receiving an 'object', which is allowed
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
                    error_msg,
                )
                return outputs

        # Final message handling (existing behavior, but kept)
        raw_msg, content_from_msg = _extract_final_message_and_content(outputs)

        if raw_msg is not None:
            new_lang = raw_msg.get("session_language")
            if isinstance(new_lang, str):
                s.session_language = new_lang
                _workflow_debug_log(f"session_language updated → {new_lang!r}")

            # We cast the result of .get() to the specific type expected by the _Session class
            s.last_apply_result = cast(dict[str, object] | None, raw_msg.get("last_apply_result"))

            content = raw_msg.get("content") or content_from_msg or ""
            meta = {
                k: v
                for k, v in raw_msg.items()
                if k not in ("content", "role", "id", "ts", "type")
            }
            meta["turn_id"] = turn_id
            meta["agent"] = role_id

            _ = _append_message_to_session(
                s,
                "agent",
                str(content or ""), # Convert to string; use empty string if content is None
                meta=meta | {"id": raw_msg.get("id") or assistant_message_id, "source": "final"},
            )

            await _maybe_apply_graph(raw_msg)

            logger.info(
                "handle_turn: final message stored session_id=%r run_id=%r content_len=%d",
                s.session_id,
                run_id,
                len(str(content or "")), # Convert to string first, fallback to empty string if None
            )
            return outputs

        # Fall back: no parsable final message payload
        final_msg = outputs.get("message")
        final_content = (
            final_msg if isinstance(final_msg, str) else "No final message returned."
        )

        _ = _append_message_to_session(
            s,
            "agent",
            final_content,
            meta={"turn_id": turn_id, "agent": role_id, "source": "no_final"},
        )
        return outputs

    finally:
        with s.run_lock:
            s.busy = False

        if on_turn_status is not None and turn_id is not None:
            try:
                await on_turn_status(
                    {
                        "status": "done",
                        "messenger": messenger,
                        "turn_id": turn_id,
                        "session_id": s.session_id,
                    }
                )
            except (ConnectionError, TimeoutError, OSError):
                logger.exception("on_turn_status(status=done) failed (turn_id=%r, session_id=%r)", turn_id, s.session_id)
