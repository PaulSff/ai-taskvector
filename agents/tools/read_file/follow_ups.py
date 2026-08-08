"""read_file tool: follow-up prompt fragments."""

REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested a file content. You must check the content.\n\n"
)

REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX = (
    "\n\nSummarize the content. If the user wanted to generate a file, output use the corresponding tool to deliver."
    "Respond in {session_language}."
)

REQUEST_FILE_CONTENT_FOLLOW_UP_USER_MESSAGE = (
    "Check out the file. Provide a brief summary, if the job is finished or needs clarifications. If we intended to generate a file (report, readme, code, etc), use the corresponding tool to ouput the action JSON block. Respond in Respond in {session_language}."
)
