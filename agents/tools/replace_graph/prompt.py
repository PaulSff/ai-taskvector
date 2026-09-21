"""replace_graph edit prompt line"""

TOOL_ACTION_PROMPT_LINE = """
- replace_graph (rebuild the entire workflow graph in one go): { "action": "replace_graph", "units": [ { "id": "...", "type": "...", "controllable": true/false } ], "connections": [ { "from": "unit_id1", "to": "unit_id2", "from_port": "port_index", "to_port": "port_index" } ] }
"""
