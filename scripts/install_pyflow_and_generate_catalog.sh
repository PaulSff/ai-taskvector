#!/usr/bin/env bash
# Install PyFlow (includes PyFlowBase) and run generate_pyflow_catalog.py.
# Creates units/pyflow/ if missing and writes units/pyflow/_catalog_generated.py.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo "Installing PyFlow..."
pip install PyFlow

echo "Running generate_pyflow_catalog.py..."
python scripts/generate_pyflow_catalog.py
