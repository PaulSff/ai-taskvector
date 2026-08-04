#!/usr/bin/env bash
# Run GUI app: sh run.sh
# Run GUI web: sh run.sh --web -p 8550
#
set -euo pipefail

# Unbuffer server output so shutdown logs can appear
python -u services/server/workflow_server.py 2>&1 &
server_pid=$!

# Forward args to flet; if --web is set but no -p/--port is provided, default to 8550
flet_args=("$@")

if printf '%s\n' "$@" | grep -q -- '--web'; then
  has_port=0
  for a in "$@"; do
    [[ "$a" == "-p" || "$a" == "--port" ]] && has_port=1
  done

  if [[ "$has_port" -eq 0 ]]; then
    flet_args+=("-p" "8550")
  fi

  flet run gui/main.py "${flet_args[@]}" 2>&1 &
else
  flet run gui/main.py 2>&1 &
fi
gui_pid=$!

shutdown_gui_then_server() {
  echo "Shutting down..."

  # GUI first
  if [[ -n "${gui_pid:-}" ]] && kill -0 "$gui_pid" 2>/dev/null; then
    kill -INT "$gui_pid" 2>/dev/null || true
    wait "$gui_pid" 2>/dev/null || true
  fi

  # Then server
  if [[ -n "${server_pid:-}" ]] && kill -0 "$server_pid" 2>/dev/null; then
    kill -INT "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
}

trap 'shutdown_gui_then_server' INT TERM

wait "$gui_pid" 2>/dev/null || true
shutdown_gui_then_server
