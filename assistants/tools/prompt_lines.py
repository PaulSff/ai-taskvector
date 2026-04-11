"""Load per-tool action prompt lines from ``assistants/tools/<tool_id>/prompt.py`` (no package __init__).

Importing ``assistants.tools.<tool_id>`` would run subpackage ``__init__.py`` files that depend on the GUI
and ``assistants.prompts``; workflow designer system prompt expansion runs during ``assistants.prompts``
import, so we load ``prompt.py`` by file path only.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

_TOOLS_ROOT = Path(__file__).resolve().parent
_TOOL_PLACEHOLDER_RE = re.compile(r'\{tool:\s*["\']?([a-z0-9_]+)["\']?\s*\}')


def get_tool_action_prompt_line(tool_id: str) -> str:
    """Return ``TOOL_ACTION_PROMPT_LINE`` from ``<tool_id>/prompt.py`` (with trailing newline)."""
    path = _TOOLS_ROOT / tool_id / "prompt.py"
    if not path.is_file():
        raise FileNotFoundError(f"No prompt.py for tool_id {tool_id!r}: {path}")
    name = f"_assistants_tools_{tool_id}_prompt"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    line = getattr(mod, "TOOL_ACTION_PROMPT_LINE", None)
    if not isinstance(line, str) or not line.strip():
        raise ValueError(f"{path} must define a non-empty str TOOL_ACTION_PROMPT_LINE")
    return line.rstrip() + "\n"


def expand_tool_action_placeholders(template: str) -> str:
    """Replace ``{tool: "id"}`` / ``{tool:id}`` with the corresponding ``TOOL_ACTION_PROMPT_LINE``."""

    def repl(m: re.Match[str]) -> str:
        return get_tool_action_prompt_line(m.group(1))

    return _TOOL_PLACEHOLDER_RE.sub(repl, template)
