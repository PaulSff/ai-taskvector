# Full stack: main app + RAG + Flet GUI + units (web_search, etc.)
# Python 3.10–3.12 per project requirements (PyTorch; RAG)
# Compatible with classic Docker (2022) and BuildKit. For "No space left on device", free disk
# or set TMPDIR/PIP_CACHE_DIR to a path on a larger drive before building.
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Install system deps useful for PyTorch/scientific stack (optional; remove if image size is critical)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy all requirement files, then install in one RUN (torch, httpx, fastapi, stable-baselines3, ollama, etc.)
COPY requirements.txt ./
COPY rag/requirements.txt ./rag/
COPY gui/requirements.txt ./gui/
COPY units/web/requirements.txt ./units/web/

RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r rag/requirements.txt && \
    pip install --no-cache-dir -r gui/requirements.txt && \
    pip install --no-cache-dir -r units/web/requirements.txt

# Copy application code
COPY . .

# Run Flet GUI (from repo root).
# Ollama: the Python client (ollama) is installed; the Ollama server is separate.
# Use docker-compose.yml to run app + Ollama together; set OLLAMA_HOST=http://ollama:11434.
# For desktop: use X11 forwarding or a display. For web UI: override with
#   flet run gui/main.py --web -p 8550
CMD ["python", "-m", "gui.main"]
