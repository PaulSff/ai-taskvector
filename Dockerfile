# Full stack: main app + RAG + Flet GUI + units (web_search, etc.)
# Python 3.10–3.12 per project requirements (PyTorch; RAG)
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Install system deps useful for PyTorch/scientific stack (optional; remove if image size is critical)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies in order for better layer caching

# 1. Main app (training, FastAPI, RL, etc.)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 2. RAG (llama-index, chromadb, docling, sentence-transformers)
COPY rag/requirements.txt ./rag/
RUN pip install --no-cache-dir -r rag/requirements.txt

# 3. Flet GUI + flet-code-editor
COPY gui/flet/requirements.txt ./gui/flet/
RUN pip install --no-cache-dir -r gui/flet/requirements.txt

# 4. Units (web_search, beautifulsoup, html2text, minify-html)
COPY units/web/requirements.txt ./units/web/
RUN pip install --no-cache-dir -r units/web/requirements.txt

# Copy application code
COPY . .

# Run Flet GUI (from repo root).
# Ollama: the Python client (ollama) is installed; the Ollama server is separate.
# Use docker-compose.yml to run app + Ollama together; set OLLAMA_HOST=http://ollama:11434.
# For desktop: use X11 forwarding or a display. For web UI: override with
#   flet run gui/flet/main.py --web -p 8550
CMD ["python", "-m", "gui.flet.main"]
