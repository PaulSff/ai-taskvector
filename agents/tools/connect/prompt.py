"""connect edit prompt line"""

TOOL_ACTION_PROMPT_LINE = """
- connect: { "action": "connect", "from": "unit_id", "to": "unit_id", "from_port": "port_index":, "to_port": "port_index" } (The ports are indexed from 0 to n-1, default is "0". Use the port index, e.g. "from_port": "0","to_port": "1")
"""
