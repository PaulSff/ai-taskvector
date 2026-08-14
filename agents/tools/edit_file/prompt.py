"""edit_file tool action JSON prompt line"""

TOOL_ACTION_PROMPT_LINE = (
    '- edit_file: { "action": "edit_file", "output_dir": "path/to/my/file", "file": { "file_name": "example.py", "replacement_1": { "line_num_ref": 126 (approximate_line_number_reference_near_the_region), "find": "    old_value = 0\n    old_other_value = 0", "replace_with": "    x = 1\n    y = 2"}, "replacement_2": { ... },  } } (use empty "replace_with":"" in order to delete)'
)
