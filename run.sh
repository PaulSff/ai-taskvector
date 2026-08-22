#!/usr/bin/env bash
#
# Run GUI app:
#   ./run.sh
#
# Run GUI web app:
#   ./run.sh --web -p 8550
#
set -euo pipefail

server_pid=""
subscriber_pid=""
poller_pid=""
ollama_pid=""
gui_pid=""
shutdown_started=0

# Start workflow server
python -u services/server/workflow_server.py 2>&1 &
server_pid=$!

# Start Telegram/ZMQ subscriber service
python -u messengers_integrations/telegram/telegram_bot_api/tg_zmq_subscriber.py 2>&1 &
subscriber_pid=$!

# Start the agentic loop poller.
#
# This process owns:
#   - FollowupCtxSubscriber
#   - AgenticTurnQueue
#   - agentic loop worker tasks
python -u -m services.agentic_loop.loop_poller 2>&1 &
poller_pid=$!

# Start Ollama
ollama serve 2>&1 &
ollama_pid=$!

# Forward arguments to Flet.
flet_args=("$@")

# If --web is supplied without -p/--port, use port 8550.
if printf '%s\n' "$@" | grep -q -- '--web'; then
  has_port=0

  for arg in "$@"; do
    if [[ "$arg" == "-p" || "$arg" == "--port" ]]; then
      has_port=1
      break
    fi
  done

  if [[ "$has_port" -eq 0 ]]; then
    flet_args+=("-p" "8550")
  fi

  flet run gui/main.py "${flet_args[@]}" 2>&1 &
else
  flet run gui/main.py 2>&1 &
fi

gui_pid=$!

shutdown_all() {
  # The function may be called by both the signal trap and the final wait.
  if [[ "$shutdown_started" -eq 1 ]]; then
    return
  fi

  shutdown_started=1
  echo "Shutting down..."

  # Stop GUI first.
  if [[ -n "$gui_pid" ]] && kill -0 "$gui_pid" 2>/dev/null; then
    echo "Stopping GUI: $gui_pid"
    kill -INT "$gui_pid" 2>/dev/null || true
    wait "$gui_pid" 2>/dev/null || true
  fi

  # Stop the agentic poller next.
  #
  # loop_poller.py handles its own shutdown order:
  #   1. Stop FollowupCtxSubscriber
  #   2. Stop AgenticTurnQueue
  #   3. Release the process lock
  if [[ -n "$poller_pid" ]] && kill -0 "$poller_pid" 2>/dev/null; then
    echo "Stopping agentic loop poller: $poller_pid"
    kill -TERM "$poller_pid" 2>/dev/null || true
    wait "$poller_pid" 2>/dev/null || true
  fi

  # Stop the external Telegram/ZMQ subscriber.
  if [[ -n "$subscriber_pid" ]] && kill -0 "$subscriber_pid" 2>/dev/null; then
    echo "Stopping Telegram/ZMQ subscriber: $subscriber_pid"
    kill -INT "$subscriber_pid" 2>/dev/null || true
    wait "$subscriber_pid" 2>/dev/null || true
  fi

  # Stop the workflow server.
  if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
    echo "Stopping workflow server: $server_pid"
    kill -INT "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi

  # Stop Ollama last.
  if [[ -n "$ollama_pid" ]] && kill -0 "$ollama_pid" 2>/dev/null; then
    echo "Stopping Ollama: $ollama_pid"
    kill -INT "$ollama_pid" 2>/dev/null || true
    wait "$ollama_pid" 2>/dev/null || true
  fi

  echo "Shutdown complete."
}

trap shutdown_all INT TERM

# Keep the launcher alive while the GUI is running.
wait "$gui_pid" 2>/dev/null || true

# Normal GUI exit.
shutdown_all
