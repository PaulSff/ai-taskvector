"""
Start Ollama server from the app when "Start Ollama with app" is enabled.
Stops the server on app exit if we started it.
Uses settings: start_ollama_with_app, ollama_executable_path.
"""
from __future__ import annotations

import atexit
import os
import subprocess
import sys
import time
from pathlib import Path

# Repo root for loading settings
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
WAIT_READY_TIMEOUT_S = 30
WAIT_POLL_INTERVAL_S = 0.5
STOP_TIMEOUT_S = 5

# Process we started (so we can stop it on exit); None if server was already running or not started
_ollama_process: subprocess.Popen | None = None


def _stop_ollama_on_exit() -> None:
    """Called at exit: terminate the Ollama process we started, if any."""
    global _ollama_process
    if _ollama_process is None:
        return
    try:
        _ollama_process.terminate()
        _ollama_process.wait(timeout=STOP_TIMEOUT_S)
        print("[Ollama] Stopped server (app exit)", flush=True)
    except subprocess.TimeoutExpired:
        _ollama_process.kill()
        _ollama_process.wait()
        print("[Ollama] Killed server (did not stop in time)", flush=True)
    except Exception as e:
        print("[Ollama] Error stopping server:", e, flush=True)
    finally:
        _ollama_process = None


atexit.register(_stop_ollama_on_exit)


def _get_ollama_executable() -> str:
    """Resolve ollama binary: from settings path, or 'ollama' (PATH)."""
    try:
        from gui.components.settings import load_settings, KEY_OLLAMA_EXECUTABLE_PATH
        path = (load_settings().get(KEY_OLLAMA_EXECUTABLE_PATH) or "").strip()
        if path:
            if os.path.isabs(path) and os.path.isfile(path):
                return path
            # Non-absolute: use as command name (e.g. ollama)
            return path
    except Exception:
        pass
    return "ollama"


def _server_is_ready(host: str = DEFAULT_OLLAMA_HOST) -> bool:
    """Return True if Ollama server responds at host."""
    try:
        import urllib.request
        url = host.rstrip("/") + "/api/tags"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as _:
            return True
    except Exception:
        return False


def start_ollama_serve() -> tuple[bool, str]:
    """
    Start `ollama serve` in the background if not already running.
    Returns (success, message). Does not start if server is already reachable.
    """
    if _server_is_ready():
        print("[Ollama] Server already running at", DEFAULT_OLLAMA_HOST, flush=True)
        return True, "Ollama already running"

    exe = _get_ollama_executable()
    print("[Ollama] Starting server:", exe, "serve", flush=True)
    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "start_new_session": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    global _ollama_process
    try:
        _ollama_process = subprocess.Popen(
            [exe, "serve"],
            **kwargs,
        )
    except FileNotFoundError:
        print("[Ollama] Error: not found:", exe, flush=True)
        return False, f"Ollama not found: {exe}. Install Ollama or set path in Settings."
    except Exception as e:
        print("[Ollama] Error:", e, flush=True)
        return False, str(e)

    # Wait for server to be ready
    for _ in range(int(WAIT_READY_TIMEOUT_S / WAIT_POLL_INTERVAL_S)):
        time.sleep(WAIT_POLL_INTERVAL_S)
        if _server_is_ready():
            print("[Ollama] Server ready at", DEFAULT_OLLAMA_HOST, flush=True)
            return True, "Ollama started"
    print("[Ollama] Timeout waiting for server", flush=True)
    return False, "Ollama started but server did not become ready in time"


def maybe_start_ollama() -> tuple[bool, str]:
    """
    If settings say "start Ollama with app", start the server. Otherwise no-op.
    Returns (started_ok, message).
    """
    try:
        from gui.components.settings import load_settings, KEY_START_OLLAMA_WITH_APP
        if not load_settings().get(KEY_START_OLLAMA_WITH_APP):
            return True, ""
    except Exception:
        return True, ""
    print("[Ollama] Start-with-app enabled, checking server...", flush=True)
    return start_ollama_serve()
