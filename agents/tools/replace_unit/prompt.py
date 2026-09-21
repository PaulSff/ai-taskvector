"""replace_unit edit prompt line"""

TOOL_ACTION_PROMPT_LINE = """
- replace_unit (replace a unit with another one while maintaining its connections): { "action": "replace_unit", "find_unit": { "id": "..." }, "replace_with": { "id": "...", "type": "...", "controllable": true/false, "params": {} } }
"""
