# shared_loop.py (drop-in replacement)

import asyncio
import threading
from contextlib import contextmanager
from threading import Thread
from typing import Optional

# shared loop globals
_shared_loop: Optional[asyncio.AbstractEventLoop] = None
_shared_loop_thread: Optional[threading.Thread] = None
_shared_loop_lock = threading.Lock()

# reference-counting for users
_shared_loop_users = 0
_shared_loop_users_lock = threading.Lock()


async def _drain_pending_tasks(loop: asyncio.AbstractEventLoop) -> None:
    # Wait for whatever is pending right now to finish naturally (no cancellation).
    pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def _start_loop(loop: asyncio.AbstractEventLoop, stop_evt: threading.Event) -> None:
    """
    Run the loop and ensure loop.close() is called from this thread when run_forever exits.
    The stop_evt will be set once the loop has been closed.

    Important: do NOT cancel tasks here. Let in-flight work finish, then close.
    """
    try:
        asyncio.set_event_loop(loop)
        loop.run_forever()
    finally:
        try:
            if not loop.is_closed():
                # Let current in-flight tasks finish before closing the loop.
                try:
                    loop.run_until_complete(_drain_pending_tasks(loop))
                except Exception:
                    pass
                loop.close()
        except Exception:
            pass
        finally:
            stop_evt.set()


def _ensure_shared_loop() -> asyncio.AbstractEventLoop:
    """
    Ensure a shared loop is running and return it (does NOT change user count).
    Use get_shared_loop() or shared_loop_user() context manager to increment the refcount.
    """
    global _shared_loop, _shared_loop_thread
    with _shared_loop_lock:
        if _shared_loop is None or _shared_loop.is_closed():
            loop = asyncio.new_event_loop()
            stop_evt = threading.Event()
            th = Thread(target=_start_loop, args=(loop, stop_evt), daemon=True)
            # attach stop event to thread for shutdown to wait on
            th._loop_stop_event = stop_evt  # type: ignore[attr-defined]
            _shared_loop = loop
            _shared_loop_thread = th
            th.start()
        return _shared_loop  # type: ignore[return-value]


def get_shared_loop() -> asyncio.AbstractEventLoop:
    """
    Start or return the shared loop and increment the user count.
    Call release_shared_loop() when done.
    """
    loop = _ensure_shared_loop()
    with _shared_loop_users_lock:
        global _shared_loop_users
        _shared_loop_users += 1
    return loop


def acquire_shared_loop() -> None:
    global _shared_loop_users
    with _shared_loop_users_lock:
        _shared_loop_users += 1


def release_shared_loop(timeout: float = 2.0) -> None:
    global _shared_loop_users
    with _shared_loop_users_lock:
        if _shared_loop_users > 0:
            _shared_loop_users -= 1
        if _shared_loop_users > 0:
            return
    shutdown_shared_loop(timeout)


def shutdown_shared_loop(timeout: float = 2.0) -> None:
    """
    Stop the shared loop and wait for the loop thread to close the loop.
    Ensures loop.close() runs on the loop thread, and that we do NOT cancel tasks.
    """
    global _shared_loop, _shared_loop_thread

    with _shared_loop_lock:
        loop = _shared_loop
        th = _shared_loop_thread
        # clear globals early so new callers create a fresh loop if needed
        _shared_loop = None
        _shared_loop_thread = None

    if loop is None:
        return

    # Ask the loop to stop (from current thread).
    try:
        loop.call_soon_threadsafe(loop.stop)
    except Exception:
        pass

    # Wait for the loop thread to signal that it has closed the loop.
    stop_evt: Optional[threading.Event] = (
        getattr(th, "_loop_stop_event", None) if th else None
    )
    if stop_evt is not None:
        stop_evt.wait(timeout)
    else:
        if th is not None:
            try:
                th.join(timeout)
            except Exception:
                pass

    # No additional loop.close here; _start_loop will close after draining.


@contextmanager
def shared_loop_user():
    """
    Context manager that increments the shared-loop refcount for the duration of the block.
    Use when scheduling work that requires the shared loop.
    """
    acquire_shared_loop()
    try:
        yield
    finally:
        release_shared_loop()
