#!/usr/bin/env bash
# Install @node-red/nodes (via npm or pnpm) and run generate_node_red_catalog.py.
# Creates units/node_red/ if missing and writes units/node_red/_catalog_generated.py.
# Requires Node.js and npm (or pnpm) on PATH.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo "Installing @node-red/nodes (in scripts/.node_red_catalog_build)..."
python scripts/generate_node_red_catalog.py

echo "Done. Catalog written to units/node_red/_catalog_generated.py"
