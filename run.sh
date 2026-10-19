#!/usr/bin/env bash
#
# Run GUI app:
#   ./run.sh
#
# Run GUI web app:
#   ./run.sh --web -p 8550
#
# Run without Ollama:
#   SKIP_OLLAMA=1 ./run.sh
#
# Run without GUI:
#   ./run.sh --no_gui
#
set -euo pipefail

server_pid=""
subscriber_pid=""
poller_pid=""
ollama_pid=""
gui_pid=""
shutdown_started=0

WEB=0
PORT=""
HOST="0.0.0.0"
NO_GUI=0

# Parse launcher args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --web)
      WEB=1
      shift
      ;;
    -p|--port)
      PORT="${2:-8550}"
      shift 2
      ;;
    --host)
      HOST="${2:-0.0.0.0}"
      shift 2
      ;;
    --no_gui)
      NO_GUI=1
      shift
      ;;
    *)
      shift
      ;;
  esac
done

# Start workflow server
python -u services/server/workflow_server.py 2>&1 &
server_pid=$!

# Start Telegram/ZMQ subscriber service
python -u messengers_integrations/telegram/telegram_bot_api/tg_zmq_subscriber.py 2>&1 &
subscriber_pid=$!

# Start the agentic loop poller
python -u -m services.agentic_loop.loop_poller 2>&1 &
poller_pid=$!

# Start Ollama unless explicitly skipped
if [[ "${SKIP_OLLAMA:-0}" != "1" ]]; then
  ollama serve 2>&1 &
  ollama_pid=$!
fi

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

trap shutdown_all INT TERM EXIT

# Launch GUI unless headless
if [[ "$NO_GUI" -eq 1 ]]; then
  echo "Running in headless mode (--no_gui)..."
  echo "Press Ctrl+C to stop services..."
  pids=()
  [[ -n "$server_pid" ]] && pids+=("$server_pid")
  [[ -n "$subscriber_pid" ]] && pids+=("$subscriber_pid")
  [[ -n "$poller_pid" ]] && pids+=("$poller_pid")
  [[ -n "$ollama_pid" ]] && pids+=("$ollama_pid")
  wait -n "${pids[@]}" 2>/dev/null || true
  exit 0
fi

if [[ "$WEB" -eq 1 ]]; then
  export FLET_WEB=1
  export FLET_SERVER_HOST="$HOST"
  export FLET_SERVER_PORT="${PORT:-8550}"
fi

python gui/main.py 2>&1 &
gui_pid=$!

wait "$gui_pid" 2>/dev/null || true
