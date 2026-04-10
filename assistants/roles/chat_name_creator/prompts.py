"""Chat filename suggestion prompt (create_filename workflow).

Canonical location: ``assistants/roles/chat_name_creator/prompts.py``.
Re-exported from ``assistants.prompts``.
"""

CREATE_FILENAME_SYSTEM = (
    "You generate concise filenames for chat logs. "
    "Return ONLY a short snake_case name (no spaces), WITHOUT extension. "
    "Use 3-8 words max. Example: workflow_roundtrip_execution"
)
