"""edit_file tool action JSON prompt line"""

TOOL_ACTION_PROMPT_LINE = (
    '- edit_file: { "action": "edit_file", "output_dir": "path/to/my/file", "file": { "file_name": "example.py" }, "replacement_1": { "find_starting_anchor_line": "def start_marker():", "find_ending_anchor_line": "def end_marker():", "insert_in_between": "    x = 1\n    y = 2" }, "replacement_2": {...} } '
    '(For each replacement define starting and ending UNIQUE anchor lines (3 LINES AT MAX), which MUST match exaclty the original file. Then provide your code snippent to insert in between these lines (insert_in_between)'
)
