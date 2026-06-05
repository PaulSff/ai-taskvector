"""
chat_orchestrator.py

Flet-independent chat orchestration for role-based agent workflows.

Primary API:
- orchestrator = ChatOrchestrator(...)
- async for event in orchestrator.send_user_message(profile=..., text=...):
      handle streaming/event (tokens, interim, status, final)
- orchestrator.register_role_handler(role_id, handler)
- orchestrator.load_session(...), persist hooks, stop_current_run(), reset_session()

Events yielded by send_user_message (dict with "type" key):
- {"type":"status","status":"Planning next moves…"}
- {"type":"token","token":"hello"}
- {"type":"inline_status","status":"..."}
- {"type":"final","message": {... final message dict saved to history ...}}
- {"type":"error","error":"message"}
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    Union,
)

from gui.chat.utils.random import _new_id
from gui.chat.utils.time import _now_ts

# ---------- Types / Protocols ----------


@dataclass
class ChatMessage:
    id: str
    ts: str
    role: str
    content: str
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = {"id": self.id, "ts": self.ts, "role": self.role, "content": self.content}
        if self.meta:
            d.update(self.meta)
        return d


@dataclass
class ChatSessionState:
    history: List[Dict[str, Any]] = field(default_factory=list)
    busy: bool = False
    has_sent_any: bool = False
    session_id: str = field(default_factory=_new_id)
    created_at: str = field(default_factory=_now_ts)
    chat_path: Optional[Path] = None
    session_language: str = ""


class RoleChatHandler(Protocol):
    """
    Implementations should provide run_turn(ctx, message_for_workflow) -> Awaitable[None]
    The handler should call ctx.run_workflow_streaming(...) to run workflows that stream tokens, or
    call ctx.append_message(...) directly for sync replies.
    """

    async def run_turn(
        self, ctx: "RoleTurnContext", message_for_workflow: str
    ) -> None: ...


@dataclass
class RoleTurnContext:
    """
    Context passed to role handlers. No UI types here; adapters will bind callbacks.
    Fields are intentionally minimal; adapters may extend if needed.
    """

    orchestrator: "ChatOrchestrator"
    profile: str
    agent_display: str
    turn_id: str
    token: int
    # Helpers provided by orchestrator (callables)
    append_message: Callable[[str, str, Dict[str, Any] | None], None]
    replace_agent_message: Callable[[Dict[str, Any]], None]
    run_workflow_streaming: Callable[..., Awaitable[Any]]
    set_inline_status: Callable[[Optional[str]], None]
    persist_debounced: Callable[[], None]
    get_state_snapshot: Callable[[], ChatSessionState]
    # Low-level: handler may set delegate request dict on this ref
    delegate_request_ref: Dict[str, Any]


# ---------- Orchestrator ----------


class ChatOrchestrator:
    """
    Framework-agnostic orchestrator.

    Constructor arguments:
    - chat_history_dir: optional Path where persistence helpers may write (or adapters can handle saving)
    - autosave_delay_s: debounce delay for persistence
    - filename_suggester: optional callable(first_message: str) -> str | Awaitable[str]
        used to suggest chat filenames (adapter can persist)
    - normalize_user_message: optional callable to normalize user input before workflow
    """

    def __init__(
        self,
        *,
        chat_history_dir: Optional[Path] = None,
        autosave_delay_s: float = 0.45,
        filename_suggester: Optional[Callable[[str], Awaitable[str] | str]] = None,
        normalize_user_message: Optional[Callable[[str], str]] = None,
        parse_session_language_command: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        self.state = ChatSessionState()
        self._role_handlers: Dict[str, RoleChatHandler] = {}
        self._on_append_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._on_stream_update_callbacks: List[Callable[[str], None]] = []
        self._on_busy_callbacks: List[Callable[[bool], None]] = []
        self._on_session_saved_callbacks: List[Callable[[], None]] = []
        self._on_delegate_request_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self.chat_history_dir = chat_history_dir
        self.autosave_delay_s = max(0.0, autosave_delay_s)
        self._filename_suggester = filename_suggester
        self._normalize = normalize_user_message or (lambda s: s)
        self._parse_session_language_command = parse_session_language_command
        # run token & cancellation
        self._run_token = 0
        self._run_lock = asyncio.Lock()
        self._persist_token = 0
        self._persist_task: Optional[asyncio.Task] = None
        # delegate request ref (mutable by handlers)
        self.delegate_request_ref: Dict[str, Any] = {}

    # ---------- Registration / callbacks ----------

    def register_role_handler(self, role_id: str, handler: RoleChatHandler) -> None:
        self._role_handlers[role_id] = handler

    def list_roles(self) -> List[str]:
        return list(self._role_handlers.keys())

    def on_append(self, cb: Callable[[Dict[str, Any]], None]) -> None:
        self._on_append_callbacks.append(cb)

    def on_stream_update(self, cb: Callable[[str], None]) -> None:
        self._on_stream_update_callbacks.append(cb)

    def on_busy(self, cb: Callable[[bool], None]) -> None:
        self._on_busy_callbacks.append(cb)

    def on_session_saved(self, cb: Callable[[], None]) -> None:
        self._on_session_saved_callbacks.append(cb)

    def on_delegate_request(self, cb: Callable[[Dict[str, Any]], None]) -> None:
        self._on_delegate_request_callbacks.append(cb)

    # ---------- Internal helpers ----------

    def _append(
        self, role: str, content: str, meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        msg = ChatMessage(
            id=_new_id(), ts=_now_ts(), role=role, content=content, meta=meta or {}
        )
        d = msg.to_dict()
        self.state.history.append(d)
        # notify adapters
        for cb in self._on_append_callbacks:
            try:
                cb(d)
            except Exception:
                pass
        # schedule persist
        self._persist_debounced()
        return d

    def _replace_agent_message(self, msg: Dict[str, Any]) -> None:
        # Notify adapter that a previously appended agent message was updated.
        for cb in self._on_append_callbacks:
            try:
                cb(msg)
            except Exception:
                pass
        self._persist_debounced()

    def _set_busy(self, v: bool) -> None:
        self.state.busy = bool(v)
        for cb in self._on_busy_callbacks:
            try:
                cb(bool(v))
            except Exception:
                pass

    def _next_run_token(self) -> int:
        self._run_token += 1
        return self._run_token

    def _is_current_run(self, token: int) -> bool:
        return token == self._run_token

    def stop_current_run(self) -> None:
        # bump token to cancel runs
        self._next_run_token()
        self._set_busy(False)

    # ---------- Persistence (adapter may override actual I/O) ----------

    def _persist_debounced(self) -> None:
        self._persist_token += 1
        token = self._persist_token

        async def _run() -> None:
            try:
                await asyncio.sleep(self.autosave_delay_s)
            except Exception:
                return
            if token != self._persist_token:
                return
            # call session saved callbacks (adapters should perform actual write)
            for cb in self._on_session_saved_callbacks:
                try:
                    cb()
                except Exception:
                    pass

        # cancel previous task if running and create new
        if self._persist_task and not self._persist_task.done():
            self._persist_task.cancel()
        self._persist_task = asyncio.create_task(_run())

    # ---------- Filename suggestion ----------

    async def _suggest_filename(self, first_message: str) -> Optional[str]:
        if not self._filename_suggester:
            return None
        try:
            res = self._filename_suggester(first_message)
            if asyncio.iscoroutine(res):
                res = await res
            return res
        except Exception:
            return None

    # ---------- Session management ----------

    def reset_session(self) -> None:
        self.state = ChatSessionState()
        self.delegate_request_ref.clear()
        # notify that session state changed (adapter listens to history length change via on_append)
        self._set_busy(False)

    def load_session_payload(self, payload: Dict[str, Any]) -> None:
        # Minimal loader: adopt fields from payload; adapters supply file-reading
        self.state.chat_path = (
            Path(payload["chat_path"]) if payload.get("chat_path") else None
        )
        self.state.session_id = payload.get("session_id", self.state.session_id)
        self.state.created_at = payload.get("created_at", self.state.created_at)
        self.state.session_language = str(payload.get("session_language") or "").strip()
        self.state.has_sent_any = bool(payload.get("has_sent_any", False))
        self.state.history = list(payload.get("messages", []))

    def get_state_snapshot(self) -> ChatSessionState:
        return self.state

    # ---------- Core: send_user_message -> async generator streaming events ----------

    async def send_user_message(
        self,
        profile: str,
        text: str,
        *,
        agent_display: Optional[str] = None,
        skip_refs: bool = False,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Send a user message to the role workflow identified by `profile` (role_id).
        Yields streaming events as dicts:
          - {"type":"status","status":...}
          - {"type":"token","token":...}
          - {"type":"inline_status","status":...}
          - {"type":"final","message": <message dict>}
          - {"type":"error","error":...}
        """
        # guard
        text = (text or "").strip()
        if not text:
            yield {"type": "error", "error": "empty_message"}
            return

        # session-language command handling (if parser provided)
        if self._parse_session_language_command:
            cmd_lang = self._parse_session_language_command(text)
            if cmd_lang is not None:
                # set session language and append ack messages
                turn_id = _new_id()
                self._set_busy(True)
                um = self._append(
                    "user",
                    text,
                    meta={
                        "turn_id": turn_id,
                        "agent": agent_display or profile,
                        "source": "user_submit",
                    },
                )
                ack_text = (
                    "Session language cleared."
                    if cmd_lang == ""
                    else f"Session language set to: {cmd_lang}"
                )
                self.state.session_language = cmd_lang
                am = self._append(
                    "agent",
                    ack_text,
                    meta={
                        "turn_id": turn_id,
                        "agent": agent_display or profile,
                        "source": "session_language_command",
                    },
                )
                self._set_busy(False)
                self._persist_debounced()
                yield {"type": "final", "message": am}
                return

        # prepare
        display_text = text
        message_for_workflow = self._normalize(display_text)
        turn_id = _new_id()
        run_token = self._next_run_token()
        self._set_busy(True)
        # Append user message (sync)
        user_msg = self._append(
            "user",
            display_text,
            meta={
                "turn_id": turn_id,
                "agent": agent_display or profile,
                "source": "user_submit",
            },
        )
        # Let adapters know we are planning
        yield {"type": "status", "status": "Planning next moves…"}
        # run handler
        handler = self._role_handlers.get(profile)
        if handler is None:
            err = f"role handler for {profile!r} not registered"
            agent_msg = self._append(
                "agent",
                err,
                meta={
                    "turn_id": turn_id,
                    "agent": agent_display or profile,
                    "source": "error",
                    "error_type": "unsupported_chat_role",
                },
            )
            self._set_busy(False)
            yield {"type": "final", "message": agent_msg}
            return

        # Provide a streaming callback mechanism: handler should call ctx.run_workflow_streaming to
        # execute long-running workflows which will call the provided stream callback that enqueues tokens.
        stream_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

        def stream_callback_piece(piece: Optional[str]) -> None:
            # called from arbitrary threads; schedule onto loop
            try:
                asyncio.get_running_loop().call_soon_threadsafe(
                    stream_queue.put_nowait, piece
                )
            except Exception:
                pass

        async def run_workflow_streaming_wrapper(
            func: Callable[..., Any], *a, **kw
        ) -> Any:
            """
            Runs a synchronous workflow function in a thread, passing stream_callback=stream_callback_piece.
            The function is expected to call stream_callback_piece(token) repeatedly and finally stream_callback_piece(None).
            Returns the function's result.
            """
            loop = asyncio.get_running_loop()

            def run_in_thread() -> Any:
                try:
                    return func(*a, **{**kw, "stream_callback": stream_callback_piece})
                except Exception as e:
                    # ensure consumer sees termination
                    try:
                        stream_callback_piece(None)
                    except Exception:
                        pass
                    raise

            return await loop.run_in_executor(None, run_in_thread)

        # Build turn context
        turn_ctx = RoleTurnContext(
            orchestrator=self,
            profile=profile,
            agent_display=agent_display or profile,
            turn_id=turn_id,
            token=run_token,
            append_message=lambda r, c, m=None: self._append(r, c, meta=m),
            replace_agent_message=lambda m: self._replace_agent_message(m),
            run_workflow_streaming=run_workflow_streaming_wrapper,
            set_inline_status=lambda s: (
                None
            ),  # adapters can subscribe to on_stream_update
            persist_debounced=lambda: self._persist_debounced(),
            get_state_snapshot=lambda: self.get_state_snapshot(),
            delegate_request_ref=self.delegate_request_ref,
        )

        # Start handler
        handler_task = asyncio.create_task(
            handler.run_turn(turn_ctx, message_for_workflow)
        )

        # Consumer: yield tokens from stream_queue as they arrive until None sentinel, or cancellation
        last_paint_ts = 0.0
        stream_buffer = ""
        stream_rich = False

        try:
            while True:
                piece = await stream_queue.get()
                # cancellation guard
                if not self._is_current_run(run_token):
                    # drain if needed, then break
                    break
                if piece is None:
                    # final flush
                    if stream_buffer:
                        # Append final agent message with buffer
                        final_msg = self._append(
                            "agent",
                            stream_buffer,
                            meta={
                                "turn_id": turn_id,
                                "agent": agent_display or profile,
                                "source": "assistant_stream_final",
                            },
                        )
                        yield {"type": "final", "message": final_msg}
                    break
                # inline status tokens prefixed by special marker? adapters/handlers can use a convention.
                # For simplicity we treat special JSON messages starting with "__status__:" as inline status
                if isinstance(piece, str) and piece.startswith("__status__:"):
                    st = piece.split(":", 1)[1]
                    yield {"type": "inline_status", "status": st}
                    continue
                # Otherwise treat as text token chunk
                if isinstance(piece, str):
                    stream_buffer += piece
                    # emit token event (consumers can render)
                    yield {"type": "token", "token": piece, "partial": stream_buffer}
                else:
                    # unknown piece type; ignore or forward
                    yield {"type": "token", "token": str(piece)}
        except asyncio.CancelledError:
            # stop requested
            handler_task.cancel()
            raise
        except Exception as ex:
            # surface errors
            yield {"type": "error", "error": str(ex)}
        finally:
            # ensure handler finishes
            try:
                await handler_task
            except asyncio.CancelledError:
                pass
            except Exception:
                # handler may have appended an error message already; still clear busy
                pass
            # if delegate_request was set by handler, notify subscribers
            dr = dict(self.delegate_request_ref) if self.delegate_request_ref else {}
            if dr:
                for cb in self._on_delegate_request_callbacks:
                    try:
                        cb(dr)
                    except Exception:
                        pass
            # If no final message was appended by stream sentinel above (e.g., handler produced separate append),
            # do not duplicate. We cannot know; adapters can track appended message ids via on_append.
            self._set_busy(False)

    # ---------- Small utility: run a sync function with streaming support (for handlers) ----------

    async def run_sync_with_streaming(self, func: Callable[..., Any], *a, **kw) -> Any:
        """
        Convenience: run sync function in executor, expecting it to accept stream_callback kw arg.
        Returns the function result.
        """
        loop = asyncio.get_running_loop()

        def run_in_thread() -> Any:
            return func(*a, **kw)

        return await loop.run_in_executor(None, run_in_thread)
