"""
LLM inference server for LLMAgent. Thin entry point for the unified inference server.

Runs the unified server with --llm-only.
POST /predict with observation + system_prompt, model_name, etc. returns { "action": [...] }.

Run:
  python -m server.llm_inference_server --port 8001
  python -m server.llm_inference_server --port 8000

Or use the unified server: python -m server.inference_server --llm-only --port 8000
"""
from __future__ import annotations

import sys

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--llm-only"] + [a for a in sys.argv[1:] if a != "--llm-only"]
    # Default port 8001 for LLM-only when not specified
    if "--port" not in sys.argv and "-p" not in sys.argv:
        sys.argv.extend(["--port", "8001"])
    from server.inference_server import main
    main()
