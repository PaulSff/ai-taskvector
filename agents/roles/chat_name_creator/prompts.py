"""Chat filename suggestion prompt (create_filename workflow).

Canonical location: ``agents/roles/chat_name_creator/prompts.py``.
Re-exported from ``agents.prompts``.
"""

CREATE_FILENAME_SYSTEM = (
    "You generate concise filenames for chat logs. "
    "Return ONLY a short snake_case name (no spaces), WITHOUT extension. "
    "Use 3-8 words max. Example: workflow_roundtrip_execution"
)
