"""edit_file tool action JSON prompt line"""

TOOL_ACTION_PROMPT_LINE = (
     '- edit_file: Edit a file in the specified folder using patch unified diff patch: { "action": "new_file", "output_dir": "/path/to/dir", "file": { "output_format": "py", "file_name": " e.g. hello_world.py", "patch": "@@ -1,5 +1,5 @@\\n-def main():\\n+def main():\\n" } }'
)
