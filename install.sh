#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/PaulSff/ai-taskvector.git"
DIR_NAME="ai-taskvector"
EXTRAS="rag,gui,llm-integrations,messengers-integrations,units-web,units-semantics,units-messengers,units-time,units-network,units-coding,mcp-integrations"
PY_MIN="3.12.6"
MODEL="gemma4:31b-cloud"

need_cmd() { command -v "$1" >/dev/null 2>&1; }

has_python() {
  if ! need_cmd python3; then return 1; fi
  python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,12,6) else 1)" >/dev/null 2>&1
}

install_homebrew() {
  if need_cmd brew; then return 0; fi
  echo "Homebrew not found. Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [ -f "/opt/homebrew/bin/brew" ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -f "/usr/local/bin/brew" ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
}

install_python() {
  echo "Python >= ${PY_MIN} not found. Installing..."
  if [ "$(uname -s)" = "Darwin" ]; then
    install_homebrew
    brew update || true
    # Ensure we have a Python 3.12+; brew formulas/patch versions vary
    if brew info python@3.12 >/dev/null 2>&1; then
      brew install "python@3.12" || brew upgrade "python@3.12" || true
      brew link --overwrite --force "python@3.12" >/dev/null 2>&1 || true
    else
      brew install python || brew upgrade python || true
    fi
  else
    # Linux: try apt first; if it fails, we'll fail clearly (distro variance)
    if [ -f /etc/debian_version ]; then
      export DEBIAN_FRONTEND=noninteractive
      apt-get update
      apt-get install -y --no-install-recommends \
        ca-certificates curl git build-essential software-properties-common
      add-apt-repository -y ppa:deadsnakes/ppa || true
      apt-get update
      apt-get install -y --no-install-recommends python3.12 python3.12-venv python3.12-dev || true
    elif [ -f /etc/redhat-release ] || [ -f /etc/centos-release ] || [ -f /etc/fedora-release ]; then
      # Best-effort for rpm-based distros
      if need_cmd dnf; then
        dnf install -y python3 python3-pip python3-virtualenv git curl || true
      else
        yum install -y python3 python3-pip python3-virtualenv git curl || true
      fi
    else
      echo "Unsupported Linux distro. Install Python >= ${PY_MIN} then re-run."
      exit 1
    fi
  fi

  if ! has_python; then
    echo "Python >= ${PY_MIN} could not be ensured by the automatic installer."
    echo "Please install Python >= ${PY_MIN} and re-run."
    exit 1
  fi
}

install_ollama_and_model() {
  if ! need_cmd ollama; then
    echo "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
  fi

  # Start service (best effort)
  ( command -v systemctl >/dev/null 2>&1 && sudo systemctl enable --now ollama ) || true
  ( [ "$(uname -s)" = "Darwin" ] && brew services start ollama ) || true

  echo "Pulling Ollama model: ${MODEL}"
  ollama pull "${MODEL}"
}

# Preconditions
if ! need_cmd curl; then
  echo "Error: curl is required."
  exit 1
fi
if ! need_cmd git; then
  echo "Error: git is required."
  exit 1
fi

# Python
if ! has_python; then
  install_python
fi

# venv + pip deps
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip setuptools wheel

# Clone
if [ ! -d "$DIR_NAME" ]; then
  git clone "$REPO_URL" "$DIR_NAME"
fi

cd "$DIR_NAME"

# Install project
python -m pip install -e ".[${EXTRAS}]"

# Ollama + model
install_ollama_and_model

echo "Done."
echo "Activate venv with: source .venv/bin/activate"
