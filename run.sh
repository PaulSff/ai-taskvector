#!/usr/bin/env bash
set -euo pipefail

# Start the server in the background
python server/workflow_server.py &
server_pid=$!

# Optional: stop server if the script is terminated
cleanup() {
  kill "$server_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Start the app (wait for server to be up can be added if you want)
python -m gui.main

# If gui exits, cleanup runs via trap
