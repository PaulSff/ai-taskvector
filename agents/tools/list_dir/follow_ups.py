"""list_dir tool: follow-up prompt fragments."""

LIST_DIR_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested the folder content discovery. You must check the result.\n\n"
)

LIST_DIR_FOLLOW_UP_SUFFIX = (
    "\n\nSummarize the folder content discovered for the user. Draw the schema, and ouput it inside the fenced block like this ``` folder_name -> files, sub-folders..```. Use the `read_file` action to if you need dive deeper into each files."
    "Respond in {session_language}."
)
