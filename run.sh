#!/usr/bin/env bash
set -euo pipefail

# Unbuffer server output so shutdown logs can appear
python -u server/workflow_server.py 2>&1 &
server_pid=$!

# Run GUI in foreground (its logs stay normal)
python -m gui.main 2>&1 &
gui_pid=$!

shutdown_gui_then_server() {
  echo "Shutting down..."

  # GUI first
  if [[ -n "${gui_pid:-}" ]] && kill -0 "$gui_pid" 2>/dev/null; then
    kill -INT "$gui_pid" 2>/dev/null || true
    wait "$gui_pid" 2>/dev/null || true
  fi

  # Then server: only SIGINT, then wait (let its own finally/logging run)
  if [[ -n "${server_pid:-}" ]] && kill -0 "$server_pid" 2>/dev/null; then
    kill -INT "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
}

trap 'shutdown_gui_then_server' INT TERM

# Wait for GUI; when it exits, shut down server in the intended order
wait "$gui_pid" 2>/dev/null || true
shutdown_gui_then_server
